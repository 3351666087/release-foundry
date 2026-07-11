(() => {
  const design = new URLSearchParams(window.location.search).get("design");
  const selected = design === "signal-form" ? "signal-form" : "release-intelligence";
  const stylesheet = document.getElementById("design-stylesheet");

  document.documentElement.dataset.design = selected;
  if (selected === "signal-form" && stylesheet) {
    stylesheet.href = "./src/signal-form.css";
    document.title = "A3 Signal/Form Dashboard";
  }
})();
