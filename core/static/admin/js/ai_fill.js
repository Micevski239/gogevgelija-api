(function ($) {
  "use strict";

  if (!window.location.pathname.match(/\/admin\/core\/event\/(add|\d+\/change)\//)) {
    return;
  }

  var FILL_URL = "/admin/core/event/ai-fill/";

  var MODAL_HTML = [
    '<div id="ai-fill-overlay" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;',
    'background:rgba(0,0,0,0.7);z-index:9999;justify-content:center;align-items:center;">',
    '<div style="background:#16213e;border:1px solid #2a2a4a;border-radius:12px;padding:32px;width:560px;',
    'max-width:95vw;box-shadow:0 20px 60px rgba(0,0,0,0.5);">',
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">',
    '<h3 style="margin:0;font-size:17px;color:#e0e0f0;font-weight:600;">✨ AI Fill from Caption</h3>',
    '<button id="ai-close" type="button" style="background:none;border:none;color:#9090b0;font-size:20px;cursor:pointer;padding:0;line-height:1;">×</button>',
    '</div>',
    '<label style="display:block;margin-bottom:6px;font-size:12px;font-weight:600;color:#9090b0;text-transform:uppercase;letter-spacing:.05em;">Platform</label>',
    '<select id="ai-platform" style="width:100%;padding:9px 12px;background:#0d1b2a;color:#e0e0f0;',
    'border:1px solid #2a2a4a;border-radius:6px;margin-bottom:16px;font-size:14px;">',
    '<option value="instagram">Instagram</option>',
    '<option value="facebook">Facebook</option>',
    '</select>',
    '<label style="display:block;margin-bottom:6px;font-size:12px;font-weight:600;color:#9090b0;text-transform:uppercase;letter-spacing:.05em;">Post Caption</label>',
    '<textarea id="ai-caption" rows="8" placeholder="Paste the social media post caption here..."',
    'style="width:100%;padding:10px 12px;background:#0d1b2a;color:#e0e0f0;border:1px solid #2a2a4a;',
    'border-radius:6px;font-size:14px;box-sizing:border-box;resize:vertical;font-family:inherit;"></textarea>',
    '<div id="ai-error" style="display:none;color:#e07070;font-size:13px;margin-top:8px;padding:8px 12px;',
    'background:#3a1a1a;border-radius:6px;border:1px solid #c0392b;"></div>',
    '<div style="display:flex;justify-content:flex-end;gap:10px;margin-top:20px;">',
    '<button id="ai-cancel" type="button" style="padding:9px 20px;border:1px solid #2a2a4a;background:transparent;',
    'color:#9090b0;border-radius:6px;cursor:pointer;font-size:14px;">Cancel</button>',
    '<button id="ai-submit" type="button" style="padding:9px 20px;background:#417690;color:#fff;border:none;',
    'border-radius:6px;cursor:pointer;font-size:14px;font-weight:600;">Generate ✨</button>',
    '</div>',
    '</div></div>',
  ].join("");

  var BAR_HTML = [
    '<div id="ai-fill-bar" style="',
    'margin:0 0 24px 0;padding:14px 20px;',
    'background:linear-gradient(135deg,#0f3460,#16213e);',
    'border:1px solid #2a2a4a;border-radius:10px;',
    'display:flex;align-items:center;justify-content:space-between;gap:16px;">',
    '<div>',
    '<div style="font-size:14px;font-weight:600;color:#e0e0f0;">✨ AI Content Generator</div>',
    '<div style="font-size:12px;color:#9090b0;margin-top:2px;">Paste a social media caption to auto-fill all fields in both languages</div>',
    '</div>',
    '<button id="ai-fill-btn" type="button" style="',
    'padding:9px 22px;background:#417690;color:#fff;border:none;border-radius:7px;',
    'cursor:pointer;font-size:14px;font-weight:600;white-space:nowrap;flex-shrink:0;',
    'transition:background .2s;">Fill from Caption</button>',
    '</div>',
  ].join("");

  function set(name, value) {
    if (!value) return;
    var el = document.getElementById("id_" + name) ||
              document.getElementById("id_" + name + "_en");
    if (!el) return;
    el.value = value;
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function fillForm(data) {
    set("title",           data.title);
    set("title_mk",        data.title_mk);
    set("description",     data.description);
    set("description_mk",  data.description_mk);
    set("location",        data.location);
    set("location_mk",     data.location_mk);
    set("date_time",       data.date_time);
    set("entry_price",     data.entry_price);
    set("entry_price_mk",  data.entry_price_mk);
    set("age_limit",       data.age_limit);
    set("age_limit_mk",    data.age_limit_mk);
    set("phone_number",    data.phone_number);
    set("facebook_url",    data.facebook_url);
    set("instagram_url",   data.instagram_url);
    set("website_url",     data.website_url);
    set("google_maps_url", data.google_maps_url);
    if (data.expectations)
      set("expectations", JSON.stringify(data.expectations, null, 2));
    if (data.expectations_mk)
      set("expectations_mk", JSON.stringify(data.expectations_mk, null, 2));
  }

  function getCsrf() {
    var el = document.querySelector("[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  function showError(msg) {
    var el = document.getElementById("ai-error");
    el.textContent = msg;
    el.style.display = "block";
  }

  function submit() {
    var caption = document.getElementById("ai-caption").value.trim();
    var platform = document.getElementById("ai-platform").value;
    if (!caption) { showError("Please paste a caption first."); return; }

    document.getElementById("ai-error").style.display = "none";
    var btn = document.getElementById("ai-submit");
    btn.disabled = true;
    btn.textContent = "Generating…";

    $.ajax({
      url: FILL_URL,
      method: "POST",
      contentType: "application/json",
      headers: { "X-CSRFToken": getCsrf() },
      data: JSON.stringify({ caption: caption, platform: platform }),
      success: function (data) {
        if (data.error) { showError(data.error); btn.disabled = false; btn.textContent = "Generate ✨"; return; }
        fillForm(data);
        $("#ai-fill-overlay").hide();
        btn.disabled = false;
        btn.textContent = "Generate ✨";
        document.getElementById("ai-caption").value = "";
      },
      error: function (xhr) {
        var msg = "Request failed.";
        try { msg = JSON.parse(xhr.responseText).error || msg; } catch (e) {}
        showError(msg);
        btn.disabled = false;
        btn.textContent = "Generate ✨";
      },
    });
  }

  $(document).ready(function () {
    $("body").append(MODAL_HTML);

    // Place the bar at the top of the form, before the first fieldset
    var firstFieldset = $("fieldset").first();
    if (firstFieldset.length) {
      firstFieldset.before(BAR_HTML);
    } else {
      $("#content-main").prepend(BAR_HTML);
    }

    $("#ai-fill-btn").on("click", function () {
      $("#ai-fill-overlay").css("display", "flex");
      document.getElementById("ai-caption").focus();
    });
    $("#ai-close, #ai-cancel").on("click", function () {
      $("#ai-fill-overlay").hide();
    });
    $("#ai-fill-overlay").on("click", function (e) {
      if (e.target === this) $(this).hide();
    });
    $(document).on("keydown", function (e) {
      if (e.key === "Escape") $("#ai-fill-overlay").hide();
    });
    $("#ai-submit").on("click", submit);
    $("#ai-caption").on("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") submit();
    });
    $("#ai-fill-btn").on("mouseenter", function () {
      $(this).css("background", "#2a5a70");
    }).on("mouseleave", function () {
      $(this).css("background", "#417690");
    });
  });

})(django.jQuery);
