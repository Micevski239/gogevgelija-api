(function ($) {
  "use strict";

  if (!window.location.pathname.match(/\/admin\/core\/promotion\/(add|\d+\/change)\//)) {
    return;
  }

  var FILL_URL    = "/admin/core/promotion/ai-fill/";
  var LISTING_URL = "/admin/core/promotion/ai-listings/";

  /* ── Modal HTML ────────────────────────────────────────────────── */
  var MODAL_HTML = [
    '<div id="ai-fill-overlay" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;',
    'background:rgba(0,0,0,0.7);z-index:9999;justify-content:center;align-items:center;">',
    '<div style="background:#16213e;border:1px solid #2a2a4a;border-radius:12px;padding:32px;width:580px;',
    'max-width:95vw;box-shadow:0 20px 60px rgba(0,0,0,0.5);max-height:90vh;overflow-y:auto;">',

    '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">',
    '<h3 style="margin:0;font-size:17px;color:#e0e0f0;font-weight:600;">✨ AI Fill from Caption</h3>',
    '<button id="ai-close" type="button" style="background:none;border:none;color:#9090b0;font-size:20px;cursor:pointer;padding:0;line-height:1;">×</button>',
    '</div>',

    '<label style="display:block;margin-bottom:6px;font-size:12px;font-weight:600;color:#9090b0;text-transform:uppercase;letter-spacing:.05em;">Listing (optional — auto-fills contact info)</label>',
    '<input id="ai-listing-search" type="text" placeholder="Search listings…"',
    ' style="width:100%;padding:9px 12px;background:#0d1b2a;color:#e0e0f0;border:1px solid #2a2a4a;',
    'border-radius:6px 6px 0 0;font-size:14px;box-sizing:border-box;font-family:inherit;">',
    '<select id="ai-listing" size="4"',
    ' style="width:100%;background:#0d1b2a;color:#e0e0f0;border:1px solid #2a2a4a;border-top:none;',
    'border-radius:0 0 6px 6px;font-size:13px;margin-bottom:4px;">',
    '<option value="">— none —</option>',
    '</select>',
    '<div id="ai-listing-preview" style="display:none;font-size:12px;color:#9090b0;margin-bottom:16px;',
    'padding:8px 10px;background:#0d1b2a;border:1px solid #2a2a4a;border-radius:6px;line-height:1.8;"></div>',

    '<label style="display:block;margin-bottom:6px;margin-top:16px;font-size:12px;font-weight:600;color:#9090b0;text-transform:uppercase;letter-spacing:.05em;">Platform</label>',
    '<select id="ai-platform" style="width:100%;padding:9px 12px;background:#0d1b2a;color:#e0e0f0;',
    'border:1px solid #2a2a4a;border-radius:6px;margin-bottom:16px;font-size:14px;">',
    '<option value="instagram">Instagram</option>',
    '<option value="facebook">Facebook</option>',
    '</select>',

    '<label style="display:block;margin-bottom:6px;font-size:12px;font-weight:600;color:#9090b0;text-transform:uppercase;letter-spacing:.05em;">Post Caption</label>',
    '<textarea id="ai-caption" rows="8" placeholder="Paste the social media post caption here…"',
    ' style="width:100%;padding:10px 12px;background:#0d1b2a;color:#e0e0f0;border:1px solid #2a2a4a;',
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

  /* ── Top bar ───────────────────────────────────────────────────── */
  var BAR_HTML = [
    '<div id="ai-fill-bar" style="',
    'margin:0 0 24px 0;padding:14px 20px;',
    'background:linear-gradient(135deg,#0f3460,#16213e);',
    'border:1px solid #2a2a4a;border-radius:10px;',
    'display:flex;align-items:center;justify-content:space-between;gap:16px;">',
    '<div>',
    '<div style="font-size:14px;font-weight:600;color:#e0e0f0;">✨ AI Content Generator</div>',
    '<div style="font-size:12px;color:#9090b0;margin-top:2px;">Select a listing, paste a caption, auto-fill all fields in both languages</div>',
    '</div>',
    '<button id="ai-fill-btn" type="button" style="',
    'padding:9px 22px;background:#417690;color:#fff;border:none;border-radius:7px;',
    'cursor:pointer;font-size:14px;font-weight:600;white-space:nowrap;flex-shrink:0;',
    'transition:background .2s;">Fill from Caption</button>',
    '</div>',
  ].join("");

  var allListings    = [];
  var selectedListing = null;

  /* ── DOM helpers ───────────────────────────────────────────────── */
  function setField(name, value) {
    if (value === null || value === undefined || value === "") return;
    var el = document.getElementById("id_" + name) ||
             document.getElementById("id_" + name + "_en");
    if (!el) return;
    el.value = value;
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function fillForm(data) {
    setField("title",          data.title);
    setField("title_mk",       data.title_mk);
    setField("description",    data.description);
    setField("description_mk", data.description_mk);
    setField("valid_until",    data.valid_until || "");
    setField("discount_code",  data.discount_code || "");
    setField("address",        data.address || "");

    if (data.tags) {
      setField("tags", JSON.stringify(data.tags));
    }
    if (data.tags_mk) {
      setField("tags_mk", JSON.stringify(data.tags_mk));
    }

    /* has_discount_code checkbox */
    if (data.has_discount_code) {
      var cb = document.getElementById("id_has_discount_code");
      if (cb) {
        cb.checked = true;
        cb.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }
  }

  function fillListing(listing) {
    if (!listing) return;
    if (listing.phone_number)    setField("phone_number",    listing.phone_number);
    if (listing.website_url)     setField("website",         listing.website_url);
    if (listing.facebook_url)    setField("facebook_url",    listing.facebook_url);
    if (listing.instagram_url)   setField("instagram_url",   listing.instagram_url);
    if (listing.address)         setField("address",         listing.address);
    if (listing.google_maps_url) setField("google_maps_url", listing.google_maps_url);
  }

  /* ── Listing helpers ───────────────────────────────────────────── */
  function renderListingOptions(filter) {
    var sel = document.getElementById("ai-listing");
    while (sel.options.length > 1) sel.remove(1);
    var term = (filter || "").toLowerCase();
    allListings.forEach(function (l) {
      if (term && l.title.toLowerCase().indexOf(term) === -1) return;
      var opt = document.createElement("option");
      opt.value = l.id;
      opt.textContent = l.title;
      sel.appendChild(opt);
    });
  }

  function showListingPreview(listing) {
    var box = document.getElementById("ai-listing-preview");
    if (!listing) { box.style.display = "none"; return; }
    while (box.firstChild) box.removeChild(box.firstChild);
    var fields = [
      ["Phone",     listing.phone_number],
      ["Website",   listing.website_url],
      ["Facebook",  listing.facebook_url],
      ["Instagram", listing.instagram_url],
      ["Address",   listing.address],
      ["Maps",      listing.google_maps_url],
    ];
    fields.forEach(function (pair) {
      if (!pair[1]) return;
      var row = document.createElement("span");
      var label = document.createElement("strong");
      label.textContent = pair[0] + ": ";
      var val = document.createTextNode(pair[1] + "  ");
      row.appendChild(label);
      row.appendChild(val);
      box.appendChild(row);
    });
    box.style.display = "block";
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
    var caption  = document.getElementById("ai-caption").value.trim();
    var platform = document.getElementById("ai-platform").value;
    if (!caption) { showError("Please paste a caption first."); return; }

    document.getElementById("ai-error").style.display = "none";
    var btn = document.getElementById("ai-submit");
    btn.disabled    = true;
    btn.textContent = "Generating…";

    $.ajax({
      url: FILL_URL,
      method: "POST",
      contentType: "application/json",
      headers: { "X-CSRFToken": getCsrf() },
      data: JSON.stringify({ caption: caption, platform: platform }),
      success: function (data) {
        btn.disabled    = false;
        btn.textContent = "Generate ✨";
        if (data.error) { showError(data.error); return; }
        fillForm(data);
        if (selectedListing) fillListing(selectedListing);
        $("#ai-fill-overlay").hide();
        document.getElementById("ai-caption").value = "";
      },
      error: function (xhr) {
        var msg = "Request failed.";
        try { msg = JSON.parse(xhr.responseText).error || msg; } catch (e) {}
        showError(msg);
        btn.disabled    = false;
        btn.textContent = "Generate ✨";
      },
    });
  }

  function loadListings() {
    $.ajax({
      url: LISTING_URL,
      method: "GET",
      headers: { "X-CSRFToken": getCsrf() },
      success: function (data) {
        allListings = data.listings || [];
        renderListingOptions("");
      },
    });
  }

  /* ── Init ──────────────────────────────────────────────────────── */
  $(document).ready(function () {
    $("body").append(MODAL_HTML);

    var firstFieldset = $("fieldset").first();
    if (firstFieldset.length) {
      firstFieldset.before(BAR_HTML);
    } else {
      $("#content-main").prepend(BAR_HTML);
    }

    loadListings();

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

    $("#ai-listing-search").on("input", function () {
      renderListingOptions(this.value);
    });

    $("#ai-listing").on("change", function () {
      var id = parseInt(this.value, 10);
      selectedListing = allListings.find(function (l) { return l.id === id; }) || null;
      showListingPreview(selectedListing);
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
