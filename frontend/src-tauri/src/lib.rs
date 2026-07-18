use std::sync::{Arc, Mutex};

use serde::Serialize;
use serde_json::Value;
use tauri::{Manager, RunEvent, State};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};
use uuid::Uuid;

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct SidecarStatus {
    state: String,
    port: Option<u16>,
    token: Option<String>,
    details: Option<Value>,
    error: Option<String>,
}

struct SidecarRuntime {
    child: Mutex<Option<CommandChild>>,
    status: Arc<Mutex<SidecarStatus>>,
}

#[tauri::command]
fn sidecar_status(runtime: State<'_, SidecarRuntime>) -> SidecarStatus {
    runtime.status.lock().expect("sidecar 状态锁已损坏").clone()
}

fn start_sidecar(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let token = Uuid::new_v4().to_string();
    let (mut events, child) = app
        .shell()
        .sidecar("looklift-engine")?
        .args(["serve", "--port", "0"])
        .env("LOOKLIFT_STARTUP_TOKEN", &token)
        .spawn()?;
    let status = Arc::new(Mutex::new(SidecarStatus {
        state: "starting".into(),
        port: None,
        token: None,
        details: None,
        error: None,
    }));
    app.manage(SidecarRuntime {
        child: Mutex::new(Some(child)),
        status: status.clone(),
    });

    tauri::async_runtime::spawn(async move {
        while let Some(event) = events.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    if let Ok(details) = serde_json::from_slice::<Value>(&line) {
                        if details.get("event").and_then(Value::as_str) == Some("ready") {
                            let port = details
                                .get("port")
                                .and_then(Value::as_u64)
                                .and_then(|value| u16::try_from(value).ok());
                            let mut current = status.lock().expect("sidecar 状态锁已损坏");
                            current.state = "ready".into();
                            current.port = port;
                            current.token = Some(token.clone());
                            current.details = Some(details);
                            current.error = None;
                        }
                    }
                }
                CommandEvent::Stderr(line) => {
                    let message = String::from_utf8_lossy(&line).trim().to_string();
                    if !message.is_empty() {
                        status.lock().expect("sidecar 状态锁已损坏").error = Some(message);
                    }
                }
                CommandEvent::Error(message) => {
                    let mut current = status.lock().expect("sidecar 状态锁已损坏");
                    current.state = "error".into();
                    current.error = Some(message);
                }
                CommandEvent::Terminated(payload) => {
                    let mut current = status.lock().expect("sidecar 状态锁已损坏");
                    if current.state != "stopping" {
                        current.state = "error".into();
                        current.error = Some(format!("sidecar 已退出：{:?}", payload.code));
                    }
                }
                _ => {}
            }
        }
    });
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![sidecar_status])
        .setup(|app| start_sidecar(app).map_err(Into::into))
        .build(tauri::generate_context!())
        .expect("无法构建 looklift 应用");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            if let Some(runtime) = handle.try_state::<SidecarRuntime>() {
                let mut status = runtime.status.lock().expect("sidecar 状态锁已损坏");
                status.state = "stopping".into();
                drop(status);
                if let Some(child) = runtime.child.lock().expect("sidecar 进程锁已损坏").take()
                {
                    let _ = child.kill();
                }
            }
        }
    });
}
