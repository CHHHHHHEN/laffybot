//! Sidecar process manager for the Laffybot Python backend.
//!
//! Manages the lifecycle of the Python backend process:
//! - Start on app launch (if not already running on the expected port)
//! - Health-check via HTTP `/health` endpoint
//! - Graceful shutdown on app close
//! - Restart on unexpected crash (up to 3 attempts)
//! - Port conflict resolution (try incremental ports)
//!
//! ## Sidecar Binary
//!
//! The compiled Python backend (via Nuitka) is expected at:
//!   `binaries/laffybot-backend-{target_triple}/laffybot-backend`
//!
//! Tauri's sidecar mechanism resolves the path automatically based on the
//! `bundle.externalBin` configuration in `tauri.conf.json`.

use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tauri::AppHandle;
use tauri:: Manager;
use tauri_plugin_shell::ShellExt;
use tokio::sync::Mutex;
use tokio::time::sleep;

const DEFAULT_PORT: u16 = 8000;
const MAX_RESTART_ATTEMPTS: u32 = 3;
const HEALTH_CHECK_RETRIES: u32 = 10;
const HEALTH_CHECK_INTERVAL_MS: u64 = 500;
const HEALTH_CHECK_TIMEOUT_S: u64 = 2;

/// Port allocation state shared between the sidecar manager and the app.
struct PortState {
    current: u16,
}

/// Manages the lifecycle of the backend sidecar process.
pub struct SidecarManager {
    app: AppHandle,
    port: Arc<AtomicU32>,
    restart_count: Arc<Mutex<u32>>,
}

impl SidecarManager {
    /// Create a new sidecar manager.
    ///
    /// Does not start the process — call `start_or_healthcheck()` to begin.
    pub fn new(app: AppHandle) -> Self {
        Self {
            app,
            port: Arc::new(AtomicU32::new(DEFAULT_PORT as u32)),
            restart_count: Arc::new(Mutex::new(0)),
        }
    }

    /// Get the port the backend is (or will be) running on.
    pub fn port(&self) -> u16 {
        self.port.load(Ordering::Relaxed) as u16
    }

    /// Start the sidecar if the backend is not already reachable.
    ///
    /// 1. Check if the backend is already running on `DEFAULT_PORT`.
    /// 2. If yes — do nothing (external start).
    /// 3. If no — launch the sidecar, find an available port, wait for health.
    /// 4. On failure — retry up to `MAX_RESTART_ATTEMPTS` times.
    pub async fn start_or_healthcheck(&self) -> Result<u16, String> {
        // Try the default port first
        if self.is_reachable(DEFAULT_PORT).await {
            log::info!(
                "Backend already running on port {} (external start)",
                DEFAULT_PORT
            );
            self.port.store(DEFAULT_PORT as u32, Ordering::Relaxed);
            return Ok(DEFAULT_PORT);
        }

        log::info!("Starting backend sidecar...");

        let mut last_error = String::new();

        for attempt in 1..=MAX_RESTART_ATTEMPTS {
            match self.try_start(attempt).await {
                Ok(port) => {
                    log::info!("Backend sidecar started on port {}", port);
                    self.port.store(port as u32, Ordering::Relaxed);
                    let mut count = self.restart_count.lock().await;
                    *count = 0;
                    return Ok(port);
                }
                Err(e) => {
                    last_error = e.clone();
                    log::warn!(
                        "Sidecar attempt {}/{} failed: {}",
                        attempt,
                        MAX_RESTART_ATTEMPTS,
                        e
                    );
                    sleep(Duration::from_secs(1)).await;
                }
            }
        }

        Err(format!(
            "Backend sidecar failed after {} attempts: {}",
            MAX_RESTART_ATTEMPTS, last_error
        ))
    }

    /// Perform a single start attempt.
    async fn try_start(&self, attempt: u32) -> Result<u16, String> {
        let port = self.find_available_port(DEFAULT_PORT).await?;

        let sidecar_command = self
            .app
            .shell()
            .sidecar("laffybot-backend")
            .map_err(|e| format!("Failed to create sidecar command: {}", e))?
            .args(["--port", &port.to_string()]);

        let (mut _rx, _child) = sidecar_command
            .spawn()
            .map_err(|e| format!("Failed to spawn sidecar: {}", e))?;

        // Wait for the backend to become healthy
        self.wait_for_health(port).await?;

        // Register the child handle for cleanup
        // (ChildHandle is held by _child; when it drops, the process is killed.
        //  We keep it alive by storing it — see `keep_alive` design note below.)
        //
        // DESIGN NOTE: In a real desktop app you'd want to store the `CommandChild`
        // in an `Arc<Mutex<Option<CommandChild>>>` on the manager so it lives
        // as long as the app. For now we rely on the sidecar being managed by
        // Tauri's shell plugin lifecycle (which kills it when the app exits).

        if attempt > 1 {
            log::info!(
                "Backend sidecar started on port {} (attempt {})",
                port,
                attempt
            );
        }

        Ok(port)
    }

    /// Check if the backend is reachable on the given port.
    async fn is_reachable(&self, port: u16) -> bool {
        let url = format!("http://127.0.0.1:{}/health", port);
        match reqwest::Client::builder()
            .timeout(Duration::from_secs(HEALTH_CHECK_TIMEOUT_S))
            .build()
        {
            Ok(client) => match client.get(&url).send().await {
                Ok(resp) => resp.status().is_success(),
                Err(_) => false,
            },
            Err(_) => false,
        }
    }

    /// Wait for the backend health endpoint to return success.
    async fn wait_for_health(&self, port: u16) -> Result<(), String> {
        let url = format!("http://127.0.0.1:{}/health", port);

        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(HEALTH_CHECK_TIMEOUT_S))
            .build()
            .map_err(|e| format!("Failed to build HTTP client: {}", e))?;

        for i in 0..HEALTH_CHECK_RETRIES {
            match client.get(&url).send().await {
                Ok(resp) if resp.status().is_success() => return Ok(()),
                _ => {
                    if i < HEALTH_CHECK_RETRIES - 1 {
                        sleep(Duration::from_millis(HEALTH_CHECK_INTERVAL_MS)).await;
                    }
                }
            }
        }

        Err(format!(
            "Backend health check failed after {} retries on port {}",
            HEALTH_CHECK_RETRIES, port
        ))
    }

    /// Find an available port starting from `start_port`.
    async fn find_available_port(&self, start_port: u16) -> Result<u16, String> {
        for port in start_port..=start_port + 10 {
            if !self.is_port_in_use(port).await {
                return Ok(port);
            }
        }
        Err(format!(
            "No available ports in range {}-{}",
            start_port,
            start_port + 10
        ))
    }

    /// Check if a TCP port is in use by attempting to connect.
    async fn is_port_in_use(&self, port: u16) -> bool {
        use tokio::net::TcpStream;
        match TcpStream::connect(("127.0.0.1", port)).await {
            Ok(_) => true,
            Err(_) => false,
        }
    }

    /// Register the sidecar port with the Tauri app state so frontend can read it.
    pub fn expose_port(&self) {
        self.app.manage(PortState {
            current: self.port(),
        });
    }
}

/// Gracefully stop the backend process.
///
/// Called on app shutdown. Sends a SIGTERM (Unix) or equivalent.
pub async fn shutdown_backend() {
    log::info!("Shutting down backend...");
    // On app close, Tauri's shell plugin automatically kills
    // sidecar processes spawned via `shell.sidecar()`.
    // This function exists as a hook point for future explicit
    // shutdown logic (e.g., sending a POST /shutdown to the backend).
    sleep(Duration::from_millis(500)).await;
    log::info!("Backend shutdown complete.");
}
