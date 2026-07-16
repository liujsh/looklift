/* GUI-T9：预览与强度 —— before/after 对比条 + 强度滑杆（U20 端到端）。
 *
 * 依赖 App.state.currentAnalysis / currentPhotoPath（panels/analyze.js 在一次
 * 分析完成后写入，并派发 `looklift:analysis-ready` 自定义事件，用法与 app.js
 * 里 `looklift:drop` 的模式一致）。独立成文件而不是塞进 analyze.js：这是一块
 * 自成一体的业务（对比条 + 强度滑杆 + 两张预览图的 blob URL 生命周期管理），
 * 职责与"提交分析、渲染分析结果文本"不同，避免 analyze.js 继续变成堆料的
 * 大文件（CLAUDE.md 分层规范：单文件职责单一）。
 *
 * 交互设计（design.md 决策 5 + tasks.md T12）：两张 <img> 绝对叠放，上层
 * after 用 `clip-path: inset(0 X% 0 0)` 由滑杆驱动——滑杆值越大，clip 掉的
 * 右侧比例越小，露出的 after 区域越多；一条 --accent 细线（.preview-divider）
 * 标记分界位置。滑杆 `input` 事件（每次拖动 tick）只做纯视觉更新：clip-path
 * + 分界线位置 + 当前值 % 文案，不发请求，保证"对比条随之平滑变化"；滑杆
 * `change` 事件（松开/键盘步进提交时触发）才以 300ms 防抖重新请求
 * `/api/preview` 换一张新 after 图——避免拖动或连续按方向键时打一串请求。
 */
(function () {
  "use strict";

  var DEBOUNCE_MS = 300;

  var els = {};
  var beforeObjectUrl = null;
  var afterObjectUrl = null;
  var debounceTimer = null;

  /** 撤销旧的 blob objectURL，防止预览图切换时内存泄漏。 */
  function revokeIfSet(url) {
    if (url) {
      URL.revokeObjectURL(url);
    }
  }

  /**
   * `POST /api/preview` 拿到渲染后的 JPEG 字节，转成 objectURL。
   * @param {number} factor 0-1
   * @returns {Promise<string>} objectURL
   */
  function fetchPreviewBlobUrl(factor) {
    var payload = {
      path: App.state.currentPhotoPath,
      analysis: App.state.currentAnalysis,
      factor: factor,
    };
    return fetch("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(function (resp) {
      if (!resp.ok) {
        return resp
          .json()
          .catch(function () {
            return {};
          })
          .then(function (data) {
            throw new Error((data && data.error) || "预览失败：" + resp.status);
          });
      }
      return resp.blob().then(function (blob) {
        return URL.createObjectURL(blob);
      });
    });
  }

  /** 重新取 after 图（当前强度）。失败时提示，但保留旧图不清空，避免闪烁到空白。 */
  function refreshAfter(factor) {
    fetchPreviewBlobUrl(factor)
      .then(function (url) {
        var old = afterObjectUrl;
        afterObjectUrl = url;
        if (els.after) {
          els.after.src = url;
        }
        revokeIfSet(old);
      })
      .catch(function (err) {
        App.toast(err.message);
      });
  }

  /** 取 before 图：factor=0，语义即"无调整渲染"，与 after 走同一条缩放
   * 管线，尺寸天然对齐；只在每次新分析结果到来时取一次，滑杆变化不影响它。 */
  function refreshBefore() {
    fetchPreviewBlobUrl(0)
      .then(function (url) {
        var old = beforeObjectUrl;
        beforeObjectUrl = url;
        if (els.before) {
          els.before.src = url;
        }
        revokeIfSet(old);
      })
      .catch(function (err) {
        App.toast(err.message);
      });
  }

  /**
   * 按滑杆当前值更新 clip-path 分隔线位置和 % 文案——纯视觉、不发请求，拖动
   * 时实时响应。
   * @param {number} value 0-100
   */
  function updateDivider(value) {
    if (els.after) {
      els.after.style.clipPath = "inset(0 " + (100 - value) + "% 0 0)";
    }
    if (els.divider) {
      els.divider.style.left = value + "%";
    }
    if (els.valueLabel) {
      els.valueLabel.textContent = value + "%";
    }
  }

  function handleSliderInput() {
    updateDivider(Number(els.slider.value));
  }

  function handleSliderChange() {
    var value = Number(els.slider.value);
    var factor = value / 100;
    App.state.currentFactor = factor; // T10 导出用：带入后续导出的强度
    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }
    debounceTimer = setTimeout(function () {
      debounceTimer = null;
      refreshAfter(factor);
    }, DEBOUNCE_MS);
  }

  /** 新分析结果到来：显示预览卡、滑杆复位到 100%，取 before + after。 */
  function handleAnalysisReady() {
    if (!els.card || !App.state.currentAnalysis || !App.state.currentPhotoPath) {
      return;
    }
    els.slider.value = "100";
    App.state.currentFactor = 1;
    updateDivider(100);
    els.card.hidden = false;
    refreshBefore();
    refreshAfter(1);
  }

  /** 开始新一轮分析：旧预览已经不代表当前照片，先隐藏预览卡并撤销旧图。 */
  function handleAnalysisReset() {
    if (debounceTimer) {
      clearTimeout(debounceTimer);
      debounceTimer = null;
    }
    revokeIfSet(beforeObjectUrl);
    revokeIfSet(afterObjectUrl);
    beforeObjectUrl = null;
    afterObjectUrl = null;
    if (els.card) {
      els.card.hidden = true;
    }
  }

  function init() {
    els.card = document.getElementById("preview-card");
    els.before = document.getElementById("preview-before");
    els.after = document.getElementById("preview-after");
    els.divider = document.getElementById("preview-divider");
    els.slider = document.getElementById("preview-intensity-slider");
    els.valueLabel = document.getElementById("preview-intensity-value");

    if (!els.card || !window.App) {
      return;
    }

    App.state.currentFactor = 1;

    els.slider.addEventListener("input", handleSliderInput);
    els.slider.addEventListener("change", handleSliderChange);

    document.addEventListener("looklift:analysis-ready", handleAnalysisReady);
    document.addEventListener("looklift:analysis-reset", handleAnalysisReset);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
