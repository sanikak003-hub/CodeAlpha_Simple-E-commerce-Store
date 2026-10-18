// Small client-side helpers for the demo store.
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll('input[type="number"][name="quantity"]').forEach((input) => {
    input.addEventListener("change", () => {
      const min = Number(input.min || 0);
      const max = Number(input.max || 9999);
      let value = Number(input.value || min);
      if (!Number.isFinite(value)) value = min;
      input.value = Math.max(min, Math.min(max, value));
    });
  });
});
