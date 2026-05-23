mod sidecar;

use sidecar::SidecarManager;
use std::sync::Arc;
use tauri::Manager;
use tokio::sync::Mutex;

/// Holds the sidecar manager so it lives for the app's lifetime.
struct AppState {
    sidecar: Arc<Mutex<SidecarManager>>,
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let handle = app.handle().clone();
            let manager = SidecarManager::new(handle.clone());

            // Store the manager in app state
            app.manage(AppState {
                sidecar: Arc::new(Mutex::new(manager)),
            });

            // Spawn a background task to start / check backend health
            let handle_clone = handle.clone();
            tauri::async_runtime::spawn(async move {
                let state = handle_clone.state::<AppState>();
                let manager_lock = state.sidecar.lock().await;

                match manager_lock.start_or_healthcheck().await {
                    Ok(port) => {
                        manager_lock.expose_port();
                        log::info!("Backend is ready on port {}", port);
                    }
                    Err(e) => {
                        log::error!("Failed to start backend: {}", e);
                    }
                }
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
