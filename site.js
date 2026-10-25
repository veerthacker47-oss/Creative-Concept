(function () {
  document.addEventListener("click", function (event) {
    var target = event.target.closest("[data-confirm]");
    if (target && !window.confirm(target.getAttribute("data-confirm"))) { event.preventDefault(); event.stopPropagation(); }
    if (event.target.closest("[data-print]")) window.print();
  });
  document.addEventListener("change", function (event) {
    var target = event.target;
    if (target.matches("[data-autosubmit]") && target.form) target.form.requestSubmit();
  });
})();
