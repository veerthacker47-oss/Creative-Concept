(function () {
  var search = document.getElementById("studentSearch");
  var rows = Array.prototype.slice.call(document.querySelectorAll("#studentRows tr[data-student]"));
  function update() {
    var q = search ? (search.value || "").toLowerCase().trim() : "";
    var entered = 0;
    rows.forEach(function (row) {
      row.hidden = !!q && row.getAttribute("data-student").indexOf(q) === -1;
      var input = row.querySelector(".mark-input");
      if (input && input.value.trim() !== "") entered++;
    });
    var counter = document.getElementById("enteredCount");
    if (counter) counter.textContent = String(entered);
  }
  if (search) search.addEventListener("input", update);
  rows.forEach(function (row) { var input = row.querySelector(".mark-input"); if (input) input.addEventListener("input", update); });
  update();
})();
