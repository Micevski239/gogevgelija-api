(function ($) {
  "use strict";

  // Only run on Event add/change pages
  if (!window.location.pathname.match(/\/admin\/core\/event\/(add|\d+\/change)\//)) {
    return;
  }

  var FILL_URL = "/admin/core/event/ai-fill/";

  var MODAL_HTML = [
    '<div id="ai-fill-overlay" style="',
    "  display:none; position:fixed; top:0; left:0; width:100%; height:100%;",
    '  background:rgba(0,0,0,0.5); z-index:9999; justify-content:center; align-items:center;">',
    '  <div style="background:#fff; border-radius:8px; padding:28px; width:520px; max-width:95vw; box-shadow:0 8px 32px rgba(0,0,0,0.2);">',
    '    <h3 style="margin:0 0 16px; font-size:16px; color:#1a1a2e;">AI Fill from Caption</h3>',
    '    <label style="display:block; margin-bottom:6px; font-size:13px; font-weight:600;">Platform</label>',
    '    <select id="ai-platform" style="width:100%; padding:8px; border:1px solid #ccc; border-radius:4px; margin-bottom:14px; font-size:13px;">',
    '      <option value="instagram">Instagram</option>',
    '      <option value="facebook">Facebook</option>',
    "    </select>",
    '    <label style="display:block; margin-bottom:6px; font-size:13px; font-weight:600;">Post Caption</label>',
    '    <textarea id="ai-caption" rows="7" placeholder="Paste the social media post caption here..."',
    '      style="width:100%; padding:8px; border:1px solid #ccc; border-radius:4px; font-size:13px; box-sizing:border-box; resize:vertical;"></textarea>',
    '    <div id="ai-error" style="display:none; color:#c0392b; font-size:13px; margin-top:8px;"></div>',
    '    <div style="display:flex; justify-content:flex-end; gap:10px; margin-top:18px;">',
    '      <button id="ai-cancel" type="button" style="padding:8px 18px; border:1px solid #ccc; background:#fff; border-radius:4px; cursor:pointer; font-size:13px;">Cancel</button>',
    '      <button id="ai-submit" type="button" style="padding:8px 18px; background:#417690; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:13px;">Generate</button>',
    "    </div>",
    "  </div>",
    "</div>",
  ].join("");

  function setField(name, value) {
    // modeltranslation may render 'title' as 'title_en' — try both
    var el =
      document.getElementById("id_" + name) ||
      document.getElementById("id_" + name + "_en");
    if (el) {
      el.value = value;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  function fillForm(data) {
    setField("title", data.title || "");
    setField("title_mk", data.title_mk || "");
    setField("description", data.description || "");
    setField("description_mk", data.description_mk || "");
    setField("location", data.location || "");
    setField("location_mk", data.location_mk || "");
    setField("date_time", data.date_time || "");
    setField("entry_price", data.entry_price || "");
    setField("entry_price_mk", data.entry_price_mk || "");
    setField("age_limit", data.age_limit || "");
    setField("age_limit_mk", data.age_limit_mk || "");

    if (data.expectations) {
      setField("expectations", JSON.stringify(data.expectations, null, 2));
    }
    if (data.expectations_mk) {
      setField("expectations_mk", JSON.stringify(data.expectations_mk, null, 2));
    }

    if (data.facebook_url) setField("facebook_url", data.facebook_url);
    if (data.instagram_url) setField("instagram_url", data.instagram_url);
  }

  function showError(msg) {
    var el = document.getElementById("ai-error");
    el.textContent = msg;
    el.style.display = "block";
  }

  function hideError() {
    var el = document.getElementById("ai-error");
    el.style.display = "none";
  }

  function openModal() {
    $("#ai-fill-overlay").css("display", "flex");
    document.getElementById("ai-caption").focus();
    hideError();
  }

  function closeModal() {
    $("#ai-fill-overlay").hide();
  }

  function getCsrfToken() {
    var el = document.querySelector("[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  function submit() {
    var caption = document.getElementById("ai-caption").value.trim();
    var platform = document.getElementById("ai-platform").value;

    if (!caption) {
      showError("Please paste a caption first.");
      return;
    }

    hideError();
    var btn = document.getElementById("ai-submit");
    btn.disabled = true;
    btn.textContent = "Generating…";

    $.ajax({
      url: FILL_URL,
      method: "POST",
      contentType: "application/json",
      headers: { "X-CSRFToken": getCsrfToken() },
      data: JSON.stringify({ caption: caption, platform: platform }),
      success: function (data) {
        if (data.error) {
          showError(data.error);
          btn.disabled = false;
          btn.textContent = "Generate";
          return;
        }
        fillForm(data);
        closeModal();
        btn.disabled = false;
        btn.textContent = "Generate";
      },
      error: function (xhr) {
        var msg = "Request failed.";
        try {
          msg = JSON.parse(xhr.responseText).error || msg;
        } catch (e) {}
        showError(msg);
        btn.disabled = false;
        btn.textContent = "Generate";
      },
    });
  }

  $(document).ready(function () {
    // Inject modal
    $("body").append(MODAL_HTML);

    // Add button after the page header
    var btn = $(
      '<button type="button" id="ai-fill-btn" style="' +
        "margin-left:12px; padding:6px 14px; background:#417690; color:#fff;" +
        "border:none; border-radius:4px; cursor:pointer; font-size:13px; vertical-align:middle;" +
        '">✨ AI Fill</button>'
    );
    $(".breadcrumbs").after(btn);

    // Event handlers
    $("#ai-fill-btn").on("click", openModal);
    $("#ai-cancel").on("click", closeModal);
    $("#ai-fill-overlay").on("click", function (e) {
      if (e.target === this) closeModal();
    });
    $(document).on("keydown", function (e) {
      if (e.key === "Escape") closeModal();
    });
    $("#ai-submit").on("click", submit);
    $("#ai-caption").on("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") submit();
    });
  });
})(django.jQuery);
