const pages = [...document.querySelectorAll(".preview-page")];
const tabs = [...document.querySelectorAll(".tab-bar [data-target]")];
const toast = document.querySelector(".toast");

function openPage(target) {
  pages.forEach((page) => page.classList.toggle("active", page.dataset.page === target));
  tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.target === target));
  window.scrollTo({ top: 0, behavior: "instant" });
}

tabs.forEach((tab) => tab.addEventListener("click", () => openPage(tab.dataset.target)));
document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => openPage(button.dataset.go)));

document.querySelectorAll("[data-demo-action]").forEach((button) => button.addEventListener("click", () => {
  showToast(`演示模式：仅检查${button.dataset.demoAction}权限，不提交审批结果`);
}));

document.querySelector("[data-demo-check]").addEventListener("click", () => showToast("诊断已更新：当前为演示模式"));

document.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll("[data-filter]").forEach((item) => item.classList.toggle("active", item === button));
  showToast(button.dataset.filter === "all" ? "显示全部告警" : `已切换到${button.textContent.trim()}`);
}));

document.querySelectorAll("[data-incident]").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll("[data-incident]").forEach((item) => item.classList.toggle("active", item === button));
  const tools = button.dataset.incident === "tools";
  document.querySelector("#incident-title").textContent = tools ? "关键工具证据完整性复核" : "退款状态链路不一致";
  document.querySelector("#incident-meta").textContent = tools ? "复核中 · 发布凭证" : "待处理 · 退款案例 03";
  document.querySelector("#incident-severity").textContent = tools ? "中风险" : "高风险";
  document.querySelector("#incident-severity").className = `pill ${tools ? "warning" : "danger"}`;
  document.querySelector("#incident-summary").textContent = tools
    ? "候选版本工具调用已补齐，仍需确认发布账本绑定。"
    : "页面显示退款完成，但后端确认动作晚于页面状态变化。";
  document.querySelector("#incident-evidence").textContent = tools
    ? "工具证据完整，版本绑定待确认"
    : "Trace、工具调用和评测证据齐全";
  document.querySelector("#incident-timeline").hidden = tools;
}));

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 1800);
}
