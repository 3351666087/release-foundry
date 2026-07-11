const grid = document.querySelector(".compare-grid");
const buttons = [...document.querySelectorAll("[data-compare-view]")];

for (const button of buttons) {
  button.addEventListener("click", () => {
    const view = button.dataset.compareView;
    grid.dataset.view = view;
    for (const item of buttons) {
      item.setAttribute("aria-pressed", String(item === button));
    }
  });
}
