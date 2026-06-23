(function ($) {
  "use strict";

  if (!window.location.pathname.match(/\/core\/promotion\/(add|\d+\/change)\//)) {
    return;
  }

  var _base       = window.location.pathname.replace(/\/core\/promotion\/.*$/, '/');
  var FILL_URL    = _base + "core/promotion/ai-fill/";
  var LISTING_URL = _base + "core/promotion/ai-listings/";

  /* ── Modal HTML ────────────────────────────────────────────────── */
  var MODAL_HTML = [
    '<div id="ai-fill-overlay" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;',
    'background:rgba(0,0,0,0.7);z-index:9999;justify-content:center;align-items:center;">',
    '<div class="ai-fill-modal">',

    '<div class="ai-fill-header">',
    '<div>',
    '<h3>AI Fill Promotion</h3>',
    '<p>Choose a listing, paste the offer caption, then fill the promotion form in both languages.</p>',
    '</div>',
    '<button id="ai-close" type="button" aria-label="Close">×</button>',
    '</div>',

    '<div class="ai-fill-grid">',
    '<section class="ai-fill-panel">',
    '<div class="ai-fill-panel-title">1. Listing <span>optional</span></div>',
    '<input id="ai-listing-search" type="text" placeholder="Search listings…"',
    ' autocomplete="off">',
    '<div id="ai-listing-results" class="ai-listing-results"></div>',
    '<div id="ai-listing-preview" class="ai-listing-preview"></div>',
    '</section>',

    '<section class="ai-fill-panel">',
    '<div class="ai-fill-panel-title">2. Caption</div>',
    '<label for="ai-platform">Platform</label>',
    '<select id="ai-platform">',
    '<option value="instagram">Instagram</option>',
    '<option value="facebook">Facebook</option>',
    '</select>',

    '<label for="ai-caption">Post Caption</label>',
    '<textarea id="ai-caption" rows="8" placeholder="Paste the social media post caption here…"',
    '></textarea>',
    '<div class="ai-caption-meta"><span id="ai-caption-count">0 characters</span><span>Cmd/Ctrl + Enter</span></div>',

    '<div id="ai-error" style="display:none;"></div>',
    '</section>',
    '</div>',

    '<div class="ai-fill-footer">',
    '<button id="ai-cancel" type="button">Cancel</button>',
    '<button id="ai-submit" type="button">Generate & Fill Promotion</button>',
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
    var box = document.getElementById("ai-listing-results");
    while (box.firstChild) box.removeChild(box.firstChild);
    var term = (filter || "").toLowerCase();
    var matches = allListings.filter(function (l) {
      return !term || l.title.toLowerCase().indexOf(term) !== -1;
    });

    if (!matches.length) {
      var empty = document.createElement("div");
      empty.className = "ai-listing-empty";
      empty.textContent = allListings.length ? "No listings found." : "Loading listings...";
      box.appendChild(empty);
      return;
    }

    matches.slice(0, 24).forEach(function (l) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ai-listing-result" + (selectedListing && selectedListing.id === l.id ? " selected" : "");

      var title = document.createElement("span");
      title.className = "ai-listing-result-title";
      title.textContent = l.title;

      var available = [
        l.phone_number,
        l.website_url,
        l.facebook_url,
        l.instagram_url,
        l.address,
        l.google_maps_url,
      ].filter(Boolean).length;
      var meta = document.createElement("span");
      meta.className = "ai-listing-result-meta";
      meta.textContent = available ? available + " contact fields available" : "No contact fields saved";

      btn.appendChild(title);
      btn.appendChild(meta);
      btn.addEventListener("click", function () {
        selectedListing = l;
        document.getElementById("ai-listing-search").value = l.title;
        renderListingOptions(l.title);
        showListingPreview(l);
      });
      box.appendChild(btn);
    });
  }

  function addPreviewRow(box, labelText, valueText) {
    if (!valueText) return false;
    var row = document.createElement("div");
    row.className = "ai-listing-preview-row";

    var label = document.createElement("div");
    label.className = "ai-listing-preview-label";
    label.textContent = labelText;

    var value = document.createElement("div");
    value.className = "ai-listing-preview-value";
    value.textContent = valueText;

    row.appendChild(label);
    row.appendChild(value);
    box.appendChild(row);
    return true;
  }

  function showListingPreview(listing) {
    var box = document.getElementById("ai-listing-preview");
    if (!listing) {
      while (box.firstChild) box.removeChild(box.firstChild);
      var emptyTitle = document.createElement("div");
      emptyTitle.className = "ai-listing-preview-title";
      emptyTitle.textContent = "No listing selected";
      var emptyNote = document.createElement("div");
      emptyNote.className = "ai-listing-preview-note";
      emptyNote.textContent = "The AI will only fill caption-based promotion fields. Contact fields stay unchanged.";
      box.appendChild(emptyTitle);
      box.appendChild(emptyNote);
      box.style.display = "block";
      return;
    }
    while (box.firstChild) box.removeChild(box.firstChild);

    var title = document.createElement("div");
    title.className = "ai-listing-preview-title";
    title.textContent = "Selected listing: " + listing.title;
    box.appendChild(title);

    var hasRows = false;
    var fields = [
      ["Phone",     listing.phone_number],
      ["Website",   listing.website_url],
      ["Facebook",  listing.facebook_url],
      ["Instagram", listing.instagram_url],
      ["Address",   listing.address],
      ["Maps",      listing.google_maps_url],
    ];
    fields.forEach(function (pair) {
      hasRows = addPreviewRow(box, pair[0], pair[1]) || hasRows;
    });

    if (!hasRows) {
      addPreviewRow(box, "Info", "No saved contact fields found for this listing.");
    }

    var note = document.createElement("div");
    note.className = "ai-listing-preview-note";
    note.textContent = "When you generate, these contact fields are copied into the promotion.";
    box.appendChild(note);

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
    el.scrollIntoView({ block: "nearest" });
  }

  function openModal() {
    $("#ai-fill-overlay").css("display", "flex");
    document.getElementById("ai-caption").focus();
    updateCaptionCount();
  }

  function updateCaptionCount() {
    var caption = document.getElementById("ai-caption");
    var counter = document.getElementById("ai-caption-count");
    if (!caption || !counter) return;
    var count = caption.value.length;
    counter.textContent = count + " character" + (count === 1 ? "" : "s");
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

    var pageTitle = $("#content h1").first();
    if (pageTitle.length) {
      pageTitle.after(BAR_HTML);
    } else {
      $("#content-main").prepend(BAR_HTML);
    }

    loadListings();

    $("#ai-fill-btn").on("click", openModal);

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
      if (selectedListing && this.value !== selectedListing.title) {
        selectedListing = null;
        showListingPreview(null);
      }
      renderListingOptions(this.value);
    });

    $("#ai-submit").on("click", submit);
    $("#ai-caption").on("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") submit();
    });
    $("#ai-caption").on("input", updateCaptionCount);

    showListingPreview(null);

    $("#ai-fill-btn").on("mouseenter", function () {
      $(this).css("background", "#2a5a70");
    }).on("mouseleave", function () {
      $(this).css("background", "#417690");
    });

    if (new URLSearchParams(window.location.search).get("ai") === "1") {
      openModal();
    }
  });

})(django.jQuery);
