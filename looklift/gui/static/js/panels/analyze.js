/* GUI-T8：分析面板（U1 端到端）—— 拖拽/选择文件 → POST /api/analyze → 轮询
 * → 编排结果展示（风格概述 / 后期步骤 / 基本面板参数）。
 *
 * 依赖 app.js 暴露的 App 对象（bindDropzone/uploadFile/api/poll/toast/state），
 * 本文件只放这一个面板的业务逻辑，避免 app.js 无限增长（见 CLAUDE.md 分层
 * 规范：单文件职责单一）。
 */
(function () {
  "use strict";

  /* 与 report.py 的 _BASIC_LABELS 保持同一份中文映射（GUI 端简洁版：只展示
   * 非零值，正负用 --accent/--muted 区分，不做 report.py 那种红蓝配色）。 */
  var BASIC_LABELS = [
    ["temperature_shift", "色温"],
    ["tint_shift", "色调"],
    ["exposure", "曝光"],
    ["contrast", "对比度"],
    ["highlights", "高光"],
    ["shadows", "阴影"],
    ["whites", "白色"],
    ["blacks", "黑色"],
    ["texture", "纹理"],
    ["clarity", "清晰度"],
    ["dehaze", "去朦胧"],
    ["vibrance", "自然饱和度"],
    ["saturation", "饱和度"],
  ];

  var els = {};
  var isAnalyzing = false;
  var cancelPoll = null;

  /**
   * 切换「分析中」态：禁用拖拽区/文件选择，避免重复提交；显示/隐藏进度条。
   * @param {boolean} submitting
   */
  function setSubmitting(submitting) {
    isAnalyzing = submitting;
    if (els.dropzone) {
      els.dropzone.setAttribute("aria-disabled", submitting ? "true" : "false");
    }
    if (els.fileInput) {
      els.fileInput.disabled = submitting;
    }
    if (els.progress) {
      els.progress.hidden = !submitting;
    }
  }

  /**
   * 渲染风格概述：衬线标题（复用 .analyze-summary 的 h3，样式走 app.css）。
   * @param {{summary?: string}} analysis
   */
  function renderSummary(analysis) {
    if (els.summary) {
      els.summary.textContent = analysis.summary || "";
    }
  }

  /**
   * 渲染后期步骤有序列表。
   * @param {{steps?: string[]}} analysis
   */
  function renderSteps(analysis) {
    if (!els.steps) {
      return;
    }
    els.steps.innerHTML = "";
    (analysis.steps || []).forEach(function (step) {
      var li = document.createElement("li");
      li.textContent = step;
      els.steps.appendChild(li);
    });
  }

  /**
   * 渲染基本面板参数：两列小表格，只展示非零值；正值用 --accent、负值用
   * --muted 区分（参考 report.py 的展示思路，GUI 里做简洁版，不用它的红蓝
   * 配色）。曝光保留两位小数，其余参数取整（与 report.py 口径一致）。
   * @param {{basic?: Object<string, number>}} analysis
   */
  function renderBasic(analysis) {
    if (!els.basic) {
      return;
    }
    els.basic.innerHTML = "";
    var basic = analysis.basic || {};
    BASIC_LABELS.forEach(function (entry) {
      var key = entry[0];
      var label = entry[1];
      var value = basic[key];
      if (!value) {
        return; // 非零值才展示
      }
      var item = document.createElement("div");
      item.className = "analyze-basic-item";

      var labelEl = document.createElement("span");
      labelEl.className = "analyze-basic-label";
      labelEl.textContent = label;

      var decimals = key === "exposure" ? 2 : 0;
      var valueEl = document.createElement("span");
      valueEl.className = "analyze-basic-value " + (value > 0 ? "is-positive" : "is-negative");
      valueEl.textContent = (value > 0 ? "+" : "") + value.toFixed(decimals);

      item.appendChild(labelEl);
      item.appendChild(valueEl);
      els.basic.appendChild(item);
    });
  }

  /**
   * 汇总渲染一次分析结果，展示结果卡片。
   * @param {object} analysis
   */
  function renderResult(analysis) {
    renderSummary(analysis);
    renderSteps(analysis);
    renderBasic(analysis);
    if (els.result) {
      els.result.hidden = false;
    }
    // 通知 panels/preview.js（GUI-T9）新分析结果就绪，可以取 before/after
    // 预览了——与 app.js 的 `looklift:drop` 同一种"自定义事件解耦面板"模式。
    document.dispatchEvent(new CustomEvent("looklift:analysis-ready"));
  }

  /**
   * 提交一次分析：`path` 是本地文件系统路径（window 模式原生拖拽）或
   * `/api/upload` 落盘后的临时路径（browser 模式/选择文件）。分析中禁止
   * 重复提交；成功拿到结果后写入 `App.state`，供后续任务（T9 滑杆、T10
   * 收藏导出）直接读取。
   * @param {string} path
   */
  function submitAnalysis(path) {
    if (!path || isAnalyzing) {
      return;
    }
    App.state.currentPhotoPath = path;
    if (els.result) {
      els.result.hidden = true;
    }
    // 旧的 before/after 预览属于上一张照片，先让 panels/preview.js 隐藏/清理掉。
    document.dispatchEvent(new CustomEvent("looklift:analysis-reset"));
    setSubmitting(true);

    var hint = els.hint ? els.hint.value.trim() : "";
    App.api("/api/analyze", { method: "POST", body: { path: path, hint: hint } })
      .then(function (data) {
        if (cancelPoll) {
          cancelPoll();
        }
        cancelPoll = App.poll(data.task_id, {
          onDone: function (result) {
            cancelPoll = null;
            App.state.currentAnalysis = result;
            setSubmitting(false);
            renderResult(result);
          },
          onError: function (message) {
            cancelPoll = null;
            setSubmitting(false);
            App.toast(message);
          },
        });
      })
      .catch(function (err) {
        setSubmitting(false);
        App.toast(err.message);
      });
  }

  /**
   * 「选择文件」`<input type=file>` 变化时：先走 `App.uploadFile` 落一份
   * 临时文件拿到路径（browser 模式；window 模式下这条路径依然可用，只是
   * 通常用不到，用户会直接拖拽), 再提交分析。
   */
  function handleFileInputChange() {
    var file = els.fileInput.files && els.fileInput.files[0];
    els.fileInput.value = ""; // 允许连续选同一个文件也能触发 change
    if (!file) {
      return;
    }
    App.uploadFile(file)
      .then(function (result) {
        submitAnalysis(result.path);
      })
      .catch(function (err) {
        App.toast(err.message);
      });
  }

  function init() {
    els.dropzone = document.getElementById("analyze-dropzone");
    els.fileInput = document.getElementById("analyze-file-input");
    els.hint = document.getElementById("analyze-hint");
    els.progress = document.getElementById("analyze-progress");
    els.result = document.getElementById("analyze-result");
    els.summary = document.getElementById("analyze-summary");
    els.steps = document.getElementById("analyze-steps");
    els.basic = document.getElementById("analyze-basic");

    if (!els.dropzone || !window.App) {
      return;
    }

    App.bindDropzone(els.dropzone, submitAnalysis);

    if (els.fileInput) {
      els.fileInput.addEventListener("change", handleFileInputChange);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
