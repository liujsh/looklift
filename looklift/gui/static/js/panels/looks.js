/* GUI-T10：风格库收藏/导出（U4 前半）+ 风格库面板（U4 后半）+ 报告页入口（U8）。
 *
 * 依赖 app.js 暴露的 App 对象（api/toast/state）。两块业务放在同一个文件里：
 * 「收藏到风格库」「导出」的控件虽然物理上长在分析结果卡片（#analyze-result，
 * panels/analyze.js 的地盘）里，语义上都是对风格库的写操作，跟"展示这次分析
 * 出的文字结果"不是一回事；分开维护避免 analyze.js 继续堆料（CLAUDE.md 分层
 * 规范：单文件职责单一），也让"风格库"这个领域的前端逻辑只有一个入口。
 *
 * 「打开报告」统一用 `window.open('/report/' + encodeURIComponent(name))`——
 * design.md 决策 3：报告页是 `report.render_report` 产出的自包含独立 HTML，
 * pywebview 窗口模式下 WebView2 支持 `window.open` 弹出原生新窗口，browser
 * 模式下就是普通新标签，两种模式前端写同一行代码，不必调用 Python 侧的
 * `webview.create_window`（那样就要区分模式，维护两套前端逻辑）。
 */
(function () {
  "use strict";

  // ─── 分析结果区：收藏到风格库 + 导出（滑杆强度带入导出，见 preview.js 写
  // 入的 App.state.currentFactor）──────────────────────────────────────

  var save = {};
  // 本次分析结果已成功收藏的名字；导出按钮据此启停——导出接口按库里存的名字
  // 找 analysis，没收藏就没有可导出的对象，先收藏再导出，顺带保证导出用的
  // 就是收藏那一刻"烤"进去的强度，不会读到跟当前照片对不上的旧条目。
  var savedLookName = null;

  function setExportEnabled(enabled) {
    if (save.exportPresetBtn) save.exportPresetBtn.disabled = !enabled;
    if (save.exportSidecarBtn) save.exportSidecarBtn.disabled = !enabled;
  }

  function handleSaveLook() {
    var name = save.nameInput ? save.nameInput.value.trim() : "";
    if (!name || !App.state.currentAnalysis) {
      return;
    }
    App.api("/api/looks", {
      method: "POST",
      body: { name: name, analysis: App.state.currentAnalysis, factor: App.state.currentFactor },
    })
      .then(function () {
        savedLookName = name;
        setExportEnabled(true);
        App.toast("已收藏到风格库：" + name);
      })
      .catch(function (err) {
        App.toast(err.message);
      });
  }

  function handleExportPreset() {
    if (!savedLookName) {
      return;
    }
    App.api("/api/looks/" + encodeURIComponent(savedLookName) + "/export", { method: "POST", body: {} })
      .then(function (data) {
        App.toast("已生成预设：" + data.preset);
      })
      .catch(function (err) {
        App.toast(err.message);
      });
  }

  function handleExportSidecar() {
    if (!savedLookName) {
      return;
    }
    var sidecar = save.sidecarInput ? save.sidecarInput.value.trim() : "";
    if (!sidecar) {
      return;
    }
    App.api("/api/looks/" + encodeURIComponent(savedLookName) + "/export", {
      method: "POST",
      body: { sidecar: sidecar },
    })
      .then(function (data) {
        App.toast("已生成 sidecar：" + data.sidecar);
      })
      .catch(function (err) {
        App.toast(err.message);
      });
  }

  /** 新一轮分析开始：旧的收藏状态不再对应当前照片，清空重来。 */
  function handleAnalysisReset() {
    savedLookName = null;
    setExportEnabled(false);
    if (save.nameInput) save.nameInput.value = "";
    if (save.sidecarInput) save.sidecarInput.value = "";
  }

  function initSaveExport() {
    save.nameInput = document.getElementById("save-look-name");
    save.saveBtn = document.getElementById("save-look-btn");
    save.exportPresetBtn = document.getElementById("export-preset-btn");
    save.exportSidecarBtn = document.getElementById("export-sidecar-btn");
    save.sidecarInput = document.getElementById("export-sidecar-path");

    if (!save.saveBtn || !window.App) {
      return;
    }
    save.saveBtn.addEventListener("click", handleSaveLook);
    if (save.exportPresetBtn) {
      save.exportPresetBtn.addEventListener("click", handleExportPreset);
    }
    if (save.exportSidecarBtn) {
      save.exportSidecarBtn.addEventListener("click", handleExportSidecar);
    }
    document.addEventListener("looklift:analysis-reset", handleAnalysisReset);
  }

  // ─── 风格库面板：卡片网格 + 打开报告 / 导出预设（U4 后半 + U8）──────────

  var panel = {};

  /** 转义成安全的 HTML 文本：借道浏览器自己的转义规则，不手写正则。 */
  function escapeText(value) {
    var div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }

  function cardHtml(look) {
    var badge = look.has_preset
      ? '<span class="badge badge-success"><span class="badge-dot"></span>预设 ✓</span>'
      : "";
    return (
      '<div class="card look-card" data-name="' + escapeText(look.name) + '">' +
      '<h3 class="look-card-name">' + escapeText(look.name) + "</h3>" +
      (badge ? '<div class="look-card-badges">' + badge + "</div>" : "") +
      '<p class="body-muted look-card-summary">' + escapeText(look.summary) + "</p>" +
      '<div class="look-card-actions">' +
      '<button type="button" class="btn btn-secondary" data-action="report">打开报告</button>' +
      '<button type="button" class="btn btn-secondary" data-action="export">导出预设</button>' +
      "</div></div>"
    );
  }

  /** 事件委托到 #looks-grid：卡片是整批重新渲染出来的，不必每次刷新后逐个
   * 重新绑定监听器。 */
  function handleGridClick(evt) {
    var btn = evt.target.closest ? evt.target.closest("[data-action]") : null;
    if (!btn) {
      return;
    }
    var card = btn.closest(".look-card");
    var name = card ? card.dataset.name : null;
    if (!name) {
      return;
    }
    if (btn.dataset.action === "report") {
      window.open("/report/" + encodeURIComponent(name));
    } else if (btn.dataset.action === "export") {
      App.api("/api/looks/" + encodeURIComponent(name) + "/export", { method: "POST", body: {} })
        .then(function (data) {
          App.toast("已生成预设：" + data.preset);
        })
        .catch(function (err) {
          App.toast(err.message);
        });
    }
  }

  function renderLooks(looks) {
    if (!panel.grid || !panel.empty) {
      return;
    }
    panel.empty.hidden = looks.length > 0;
    panel.grid.innerHTML = looks.map(cardHtml).join("");
  }

  function refreshLooks() {
    App.api("/api/looks")
      .then(function (data) {
        renderLooks(data.looks || []);
      })
      .catch(function (err) {
        App.toast(err.message);
      });
  }

  function initPanel() {
    panel.grid = document.getElementById("looks-grid");
    panel.empty = document.getElementById("looks-empty");
    if (!panel.grid || !window.App) {
      return;
    }
    panel.grid.addEventListener("click", handleGridClick);
    document.addEventListener("looklift:panel-shown", function (evt) {
      if (evt.detail && evt.detail.name === "looks") {
        refreshLooks();
      }
    });
  }

  function init() {
    initSaveExport();
    initPanel();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
