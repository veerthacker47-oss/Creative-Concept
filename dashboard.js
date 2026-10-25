(function () {
  var root = document.getElementById("stats");
  if (!root) return;
  var url = root.getAttribute("data-stats-url");
  function inr(paise) {
    var parts = (paise / 100).toFixed(2).split(".");
    var whole = parts[0], out = whole.slice(-3);
    whole = whole.slice(0, -3);
    while (whole.length > 2) { out = whole.slice(-2) + "," + out; whole = whole.slice(0, -2); }
    if (whole) out = whole + "," + out;
    return "₹" + out + "." + parts[1];
  }
  function refresh() {
    fetch(url, { credentials: "same-origin", headers: { "Accept": "application/json" } })
      .then(function (r) { if (r.status === 401 || r.redirected) { window.location.reload(); return null; } if (!r.ok) throw new Error("Refresh failed"); return r.json(); })
      .then(function (data) {
        if (!data) return;
        var updated = document.getElementById("updated");
        if (updated) updated.textContent = data.updated_at;
        root.querySelectorAll("[data-k]").forEach(function (el) {
          var key = el.getAttribute("data-k");
          if (key === "collected_fmt") el.textContent = inr(data.collected_this_month_paise);
          else if (key === "outstanding_fmt") el.textContent = inr(data.outstanding_paise);
          else if (key === "attendance_pct_fmt") el.textContent = data.attendance_pct_today === null ? "—" : Number(data.attendance_pct_today).toFixed(1) + "%";
          else if (Object.prototype.hasOwnProperty.call(data, key)) el.textContent = data[key];
        });
      }).catch(function () { /* Keep the last valid data visible while offline. */ });
  }
  window.setInterval(refresh, 30000);
})();
