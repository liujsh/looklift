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
