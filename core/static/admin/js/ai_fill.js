(function () {
  "use strict";

  if (!window.location.pathname.match(/\/admin\/core\/event\/(add|\d+\/change)\//)) {
    return;
  }

  var hash = window.location.hash;
  if (!hash.startsWith("#gg:")) return;

  var payload;
  try {
    payload = JSON.parse(decodeURIComponent(atob(hash.slice(4))));
    history.replaceState(null, "", window.location.pathname);
  } catch (e) {
    console.error("AI Fill decode error:", e);
    return;
  }

  function set(name, value) {
    if (!value) return;
    var el = document.getElementById("id_" + name) ||
              document.getElementById("id_" + name + "_en");
    if (!el) return;
    el.value = value;
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function fill(data, listingIds, categoryId) {
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

    if (data.expectations) {
      set("expectations", JSON.stringify(data.expectations, null, 2));
    }
    if (data.expectations_mk) {
      set("expectations_mk", JSON.stringify(data.expectations_mk, null, 2));
    }

    if (categoryId) {
      var cat = document.getElementById("id_category");
      if (cat) {
        cat.value = String(categoryId);
        cat.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }

    if (listingIds && listingIds.length && typeof SelectBox !== "undefined") {
      var from = document.getElementById("id_listings_from");
      if (from) {
        for (var i = 0; i < from.options.length; i++) {
          if (listingIds.indexOf(Number(from.options[i].value)) !== -1) {
            from.options[i].selected = true;
          }
        }
        SelectBox.move("id_listings_from", "id_listings_to");
      }
    }
  }

  function run() {
    fill(payload.eventContent, payload.listingIds || [], payload.categoryId || "");
  }

  // Wait for DOM to be fully ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }

})();
