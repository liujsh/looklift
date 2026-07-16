/* 前端应用：面板切换、fetch 调用、轮询、拖拽处理、强度滑杆联动。
 * 本文件目前只实现 SPA 壳的通用能力（App 对象），业务面板逻辑由后续任务接入。
 */
(function () {
  "use strict";

  var PANELS = ["analyze", "looks", "settings"];
  var DEFAULT_PANEL = "analyze";
  var STORAGE_KEY = "looklift.lastPanel";

  var App = {};

  /**
   * 切换到指定面板：显示 #panel-<name>、隐藏其余面板（用 hidden 属性），
   * 同步导航按钮的激活态（aria-current），并把当前面板记进 sessionStorage
   * 供下次打开时恢复。未知面板名会退回默认面板。
   * @param {string} name 面板名：analyze / looks / settings
   */
  App.show = function (name) {
    if (PANELS.indexOf(name) === -1) {
      name = DEFAULT_PANEL;
    }
    PANELS.forEach(function (panelName) {
      var panel = document.getElementById("panel-" + panelName);
      if (panel) {
        panel.hidden = panelName !== name;
      }
    });
    document.querySelectorAll(".nav-item").forEach(function (btn) {
      if (btn.dataset.panel === name) {
        btn.setAttribute("aria-current", "page");
      } else {
        btn.removeAttribute("aria-current");
      }
    });
    try {
      sessionStorage.setItem(STORAGE_KEY, name);
    } catch (err) {
      /* sessionStorage 不可用（如隐私模式）时静默忽略，不影响面板切换本身 */
    }
  };

  /**
   * fetch 封装：自动带 JSON 请求头；非 2xx 响应会抛出 Error，
   * 优先用服务端 JSON body 里的 `error` 字段作为错误信息。
   * @param {string} path 请求路径，如 "/api/config"
   * @param {RequestInit} [opts] fetch 选项；body 若是普通对象会自动 JSON.stringify
   * @returns {Promise<any>} 解析后的响应 JSON
   */
  App.api = function (path, opts) {
    opts = opts || {};
    var headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    var body = opts.body;
    if (body && typeof body === "object") {
      body = JSON.stringify(body);
    }
    return fetch(path, Object.assign({}, opts, { headers: headers, body: body })).then(function (resp) {
      return resp
        .json()
        .catch(function () {
          return {};
        })
        .then(function (data) {
          if (!resp.ok) {
            throw new Error((data && data.error) || "请求失败：" + resp.status);
          }
          return data;
        });
    });
  };

  /**
   * 轮询 `/api/tasks/<id>`，直到状态不再是 running 为止。
   * @param {string} taskId 任务 id
   * @param {{onDone?: (result: any) => void, onError?: (message: string) => void, interval?: number}} [handlers]
   * @returns {() => void} 取消轮询的函数
   */
  App.poll = function (taskId, handlers) {
    handlers = handlers || {};
    var interval = handlers.interval || 800;
    var cancelled = false;
    var timer = null;

    function tick() {
      if (cancelled) {
        return;
      }
      App.api("/api/tasks/" + encodeURIComponent(taskId))
        .then(function (task) {
          if (cancelled) {
            return;
          }
          if (task.status === "done") {
            if (handlers.onDone) handlers.onDone(task.result);
          } else if (task.status === "error") {
            if (handlers.onError) handlers.onError(task.error);
          } else {
            timer = setTimeout(tick, interval);
          }
        })
        .catch(function (err) {
          if (!cancelled && handlers.onError) {
            handlers.onError(err.message);
          }
        });
    }

    tick();
    return function cancel() {
      cancelled = true;
      if (timer) {
        clearTimeout(timer);
      }
    };
  };

  /**
   * 显示一条短暂提示（token 样式），自动淡出。
   * @param {string} message 提示文案
   */
  App.toast = function (message) {
    var root = document.getElementById("toast-root");
    if (!root) {
      return;
    }
    var el = document.createElement("div");
    el.className = "toast";
    el.textContent = message;
    root.appendChild(el);
    requestAnimationFrame(function () {
      el.classList.add("is-visible");
    });
    setTimeout(function () {
      el.classList.remove("is-visible");
      setTimeout(function () {
        el.remove();
      }, 200);
    }, 2600);
  };

  /**
   * pywebview 窗口模式下，Python 侧收到原生拖放事件（决策 4：
   * `window.dom.document.events.drop` 拿到 `pywebviewFullPath`）后，通过
   * `window.evaluate_js` 回推调用这里，转发成一个 DOM 自定义事件
   * `looklift:drop`，供 App.bindDropzone 消费。
   * @param {string[]} paths 绝对文件路径列表
   */
  App.onNativeDrop = function (paths) {
    document.dispatchEvent(new CustomEvent("looklift:drop", { detail: { paths: paths || [] } }));
  };

  /**
   * 把一个 File 以 FormData 上传到 `POST /api/upload`（browser 模式专用，
   * 见 design.md 决策 4：浏览器标签页拿不到真实文件系统路径，只能先落一份
   * 临时文件）。不复用 App.api，因为 FormData 请求不能带 JSON 的
   * Content-Type 头。
   * @param {File} file
   * @returns {Promise<{path: string}>}
   */
  App.uploadFile = function (file) {
    var formData = new FormData();
    formData.append("file", file, file.name);
    return fetch("/api/upload", { method: "POST", body: formData }).then(function (resp) {
      return resp
        .json()
        .catch(function () {
          return {};
        })
        .then(function (data) {
          if (!resp.ok) {
            throw new Error((data && data.error) || "上传失败：" + resp.status);
          }
          return data;
        });
    });
  };

  /**
   * 通用拖拽区绑定：window 模式下走 `looklift:drop` 拿到的原生绝对路径（零
   * 拷贝），browser 模式下对每个拖入的 File 调 App.uploadFile 落临时文件再
   * 拿路径。用 `window.__looklift_native_drop_ready` 同步区分两种模式——
   * pywebview 在窗口 `loaded` 事件后会把这个全局标记置为 `true`（见
   * app.py 的 `_register_drop_bridge`）；标记为真就说明原生路径会通过
   * `looklift:drop` 到达，这里不再重复走一遍浏览器式上传（早先版本用「等
   * 60ms 看原生事件有没有到」的猜测式去重，没有真实 pywebview 环境验证过
   * 时序，评审后改成这个确定性标记）。
   * @param {HTMLElement} el 拖拽区元素
   * @param {(path: string) => void} onPath 拿到文件路径后的回调
   */
  App.bindDropzone = function (el, onPath) {
    if (!el) {
      return;
    }

    document.addEventListener("looklift:drop", function (evt) {
      (evt.detail.paths || []).forEach(onPath);
    });

    el.addEventListener("dragover", function (evt) {
      evt.preventDefault();
    });

    el.addEventListener("drop", function (evt) {
      evt.preventDefault();
      if (window.__looklift_native_drop_ready === true) {
        return; // window 模式：原生路径走 looklift:drop，这里不重复处理
      }
      var files = (evt.dataTransfer && evt.dataTransfer.files) || [];
      Array.prototype.forEach.call(files, function (file) {
        App.uploadFile(file)
          .then(function (result) {
            onPath(result.path);
          })
          .catch(function (err) {
            App.toast(err.message);
          });
      });
    });
  };

  /**
   * 初始化：绑定导航点击事件，恢复上次打开的面板（无记录则用默认面板）。
   */
  function init() {
    document.querySelectorAll(".nav-item").forEach(function (btn) {
      btn.addEventListener("click", function () {
        App.show(btn.dataset.panel);
      });
    });
    var last = null;
    try {
      last = sessionStorage.getItem(STORAGE_KEY);
    } catch (err) {
      /* 忽略：退回默认面板 */
    }
    App.show(last || DEFAULT_PANEL);
  }

  document.addEventListener("DOMContentLoaded", init);

  window.App = App;
})();
