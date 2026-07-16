/* 前端应用：面板切换、fetch 调用、轮询、拖拽处理、强度滑杆联动。
 * 本文件目前只实现 SPA 壳的通用能力（App 对象），业务面板逻辑由后续任务接入。
 */
(function () {
  "use strict";

  var PANELS = ["analyze", "looks", "settings"];
  var DEFAULT_PANEL = "analyze";
  var STORAGE_KEY = "looklift.lastPanel";
  var WIZARD_DISMISS_KEY = "looklift.wizardDismissed";

  var App = {};

  /**
   * 跨面板共享状态。`currentAnalysis`/`currentPhotoPath` 由分析面板
   * （panels/analyze.js）在一次分析完成后写入，后续任务（T9 强度滑杆、
   * T10 收藏导出)直接读这两个字段，不用重新请求一遍。
   * @type {{currentAnalysis: (object|null), currentPhotoPath: (string|null)}}
   */
  App.state = {
    currentAnalysis: null,
    currentPhotoPath: null,
  };

  /**
   * 切换到指定面板：显示 #panel-<name>、隐藏其余面板（用 hidden 属性），
   * 同步导航按钮的激活态（aria-current），并把当前面板记进 sessionStorage
   * 供下次打开时恢复。未知面板名会退回默认面板。派发自定义事件
   * `looklift:panel-shown`（detail: {name}）——与 `looklift:drop`/
   * `looklift:analysis-ready` 同一种"自定义事件解耦面板"模式，供
   * panels/looks.js 在进入风格库面板时拉取 `GET /api/looks` 刷新列表，不用
   * app.js 反过来认识某个具体面板的业务逻辑。
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
    document.dispatchEvent(new CustomEvent("looklift:panel-shown", { detail: { name: name } }));
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
   * 把 `GET /api/config` 返回的状态回填进一个配置表单：provider 单选项按
   * `cfg.provider` 选中；model/base_url 回填当前值；api_key 输入框故意
   * 保持空——后端从不把已保存的密钥吐回来（见 api._get_config 的注释），
   * 这里只用 `cfg.has_key` 调整 placeholder 提示"已经存过一份"。
   * @param {HTMLFormElement} form
   * @param {{provider: string, model: string, has_key: boolean}} cfg
   */
  function applyConfigToForm(form, cfg) {
    var providerInput = form.querySelector('[name="provider"][value="' + cfg.provider + '"]');
    if (providerInput) {
      providerInput.checked = true;
    }
    var modelInput = form.querySelector('[name="model"]');
    if (modelInput) {
      modelInput.value = cfg.model || "";
    }
    var apiKeyInput = form.querySelector('[name="api_key"]');
    if (apiKeyInput) {
      apiKeyInput.value = "";
      apiKeyInput.placeholder = cfg.has_key ? "已保存 · 留空则不修改" : "sk-...";
    }
  }

  /**
   * 给一个配置表单（#settings-form 或向导里克隆出来的那份）挂 submit 处理：
   * 读表单值 → POST /api/config → 成功后回调 `onSaved`，失败用 App.toast
   * 提示错误（后端返回的中文 `error` 文案）。两处表单结构完全一致，共用同
   * 一段绑定逻辑，避免维护两份几乎相同的 fetch 代码。
   * @param {HTMLFormElement} form
   * @param {() => void} onSaved
   */
  function bindConfigForm(form, onSaved) {
    form.addEventListener("submit", function (evt) {
      evt.preventDefault();
      var data = new FormData(form);
      var payload = {
        provider: data.get("provider") || "auto",
        model: data.get("model") || "",
        api_key: data.get("api_key") || "",
        base_url: data.get("base_url") || "",
      };
      App.api("/api/config", { method: "POST", body: payload })
        .then(function () {
          if (onSaved) {
            onSaved();
          }
        })
        .catch(function (err) {
          App.toast(err.message);
        });
    });
  }

  /**
   * 刷新「设置」面板表单当前显示的配置状态（初始化时、以及每次保存成功后
   * 调用，保证 api_key 的 placeholder 随 has_key 变化）。
   */
  function refreshSettingsForm() {
    var form = document.getElementById("settings-form");
    if (!form) {
      return;
    }
    App.api("/api/config")
      .then(function (cfg) {
        applyConfigToForm(form, cfg);
      })
      .catch(function () {
        /* 配置探活失败不影响表单本身可用，静默忽略 */
      });
  }

  /**
   * 关闭首次配置向导：本次会话（sessionStorage）记住不再自动弹出，隐藏遮罩。
   */
  function dismissWizard() {
    try {
      sessionStorage.setItem(WIZARD_DISMISS_KEY, "1");
    } catch (err) {
      /* sessionStorage 不可用时静默忽略：本次会话内向导可能重复弹出一次 */
    }
    var wizard = document.getElementById("wizard");
    if (wizard) {
      wizard.hidden = true;
    }
  }

  /**
   * 代码评审修订（Important）：`cloneNode(true)` 会把 `id="settings-model"`/
   * `id="settings-api-key"` 这些 id 原样复制一份，导致向导（用户首屏就看到
   * 的东西）和隐藏的设置面板同时存在两份相同 id——点向导里的 `<label>` 有
   * 概率把焦点带去隐藏面板里的同名 input。这里把克隆节点内部所有 `[id]`
   * 元素的 id 换成不冲突的新值（`settings-` 前缀替换成 `wizard-`，没有该
   * 前缀的就直接加 `wizard-` 前缀），并同步改写引用它们的 `label[for]`。
   * @param {HTMLElement} clone 已从原表单克隆出来、尚未插入文档的节点
   */
  function _dedupeClonedIds(clone) {
    clone.querySelectorAll("[id]").forEach(function (el) {
      var oldId = el.id;
      var newId = oldId.indexOf("settings-") === 0 ? "wizard-" + oldId.slice("settings-".length) : "wizard-" + oldId;
      el.id = newId;
      clone.querySelectorAll('label[for="' + oldId + '"]').forEach(function (label) {
        label.setAttribute("for", newId);
      });
    });
  }

  /**
   * 展示首次配置向导：把 #settings-form 的表单结构克隆一份塞进向导容器
   * （design.md 决策「首次配置向导内容复用 .form/.field 配方」——字段定义
   * 只在 HTML 里写一份，向导用克隆节点而不是重复标记，避免两处表单字段
   * 后续改动时漏改一处），回填当前配置状态，挂 submit 处理（保存成功即
   * 关闭向导 + toast 提示）。克隆节点内部的 id 必须先经 `_dedupeClonedIds`
   * 改写掉，再插入文档，避免和隐藏的设置面板出现重复 id。
   * @param {{provider: string, model: string, has_key: boolean}} cfg
   */
  function showWizard(cfg) {
    var wizard = document.getElementById("wizard");
    var slot = document.getElementById("wizard-form-slot");
    var settingsForm = document.getElementById("settings-form");
    if (!wizard || !slot || !settingsForm) {
      return;
    }
    var clone = settingsForm.cloneNode(true);
    clone.id = "wizard-form";
    _dedupeClonedIds(clone);
    var submitBtn = clone.querySelector('button[type="submit"]');
    if (submitBtn) {
      submitBtn.textContent = "保存并开始";
    }
    slot.innerHTML = "";
    slot.appendChild(clone);
    applyConfigToForm(clone, cfg);
    bindConfigForm(clone, function () {
      dismissWizard();
      App.toast("已保存");
      refreshSettingsForm();
    });
    wizard.hidden = false;
  }

  /**
   * 配置向导 + 设置表单的初始化：绑定「设置」面板表单的保存；探活
   * `GET /api/config`，未配置且本次会话没跳过过时弹首次配置向导（design.md
   * 风险清单「首次配置向导卡死」——探活失败/超时也不阻塞主界面，直接跳过
   * 弹窗，不影响库面板/报告浏览）。
   */
  function initConfig() {
    var settingsForm = document.getElementById("settings-form");
    if (settingsForm) {
      bindConfigForm(settingsForm, function () {
        App.toast("已保存");
        refreshSettingsForm();
      });
    }
    refreshSettingsForm();

    var skipBtn = document.getElementById("wizard-skip");
    if (skipBtn) {
      skipBtn.addEventListener("click", dismissWizard);
    }

    var alreadyDismissed = false;
    try {
      alreadyDismissed = sessionStorage.getItem(WIZARD_DISMISS_KEY) === "1";
    } catch (err) {
      /* sessionStorage 不可用时视为未跳过，仍走探活弹窗逻辑 */
    }
    if (alreadyDismissed) {
      return;
    }
    App.api("/api/config")
      .then(function (cfg) {
        if (!cfg.configured) {
          showWizard(cfg);
        }
      })
      .catch(function () {
        /* 探活失败：不弹向导，不阻塞主界面（卡死是风险清单明确要避免的） */
      });
  }

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
    initConfig();
  }

  document.addEventListener("DOMContentLoaded", init);

  window.App = App;
})();
