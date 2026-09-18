/*
 * Frontend-only demo contract for the future client restaurant analytics API.
 * Keep this data out of the existing backend mock routes: production does not
 * expose business analytics yet, so business.js can later swap this source for
 * a real API adapter without changing the UI contract.
 */
(function () {
  "use strict";

  const points = [
    { id: 1, client: "ИП Агафонов", name: "Шаверма на Центральной", city: "Санкт-Петербург", address: "ул. Центральная, 18", active: true, deliveryEnabled: true },
    { id: 2, client: "ООО Индия Фуд", name: "Шаверма Индия", city: "Санкт-Петербург", address: "пр. Испытателей, 15", active: true, deliveryEnabled: false },
    { id: 3, client: "ИП Соколова", name: "Гриль на Лесной", city: "Санкт-Петербург", address: "Лесной пр., 63", active: true, deliveryEnabled: true },
    { id: 4, client: "ООО Ночной город", name: "Ночной проспект", city: "Санкт-Петербург", address: "Лиговский пр., 91", active: false, deliveryEnabled: true },
  ];

  const periods = {
    today: {
      label: "Сегодня",
      metrics: { orders: 218, turnover: 183640, active: 17, averageCheck: 842, cancelled: 9, tasks: 12, storesOpen: 3 },
      trend: [42, 58, 71, 64, 82, 92, 76, 100],
      statuses: [{ label: "Новые", value: 4, tone: "amber" }, { label: "Ожидают кухню", value: 3, tone: "warning" }, { label: "Готовятся", value: 6, tone: "amber" }, { label: "Готовы к выдаче", value: 4, tone: "success" }],
      stores: [
        { pointId: 1, orders: 81, turnover: 70280, employees: 8, tasks: 5, deliveryOrders: 24, deliveryTurnover: 22140 },
        { pointId: 2, orders: 66, turnover: 54840, employees: 6, tasks: 4, deliveryOrders: 0, deliveryTurnover: 0 },
        { pointId: 3, orders: 49, turnover: 42100, employees: 5, tasks: 3, deliveryOrders: 17, deliveryTurnover: 15860 },
        { pointId: 4, orders: 22, turnover: 16420, employees: 3, tasks: 0, deliveryOrders: 6, deliveryTurnover: 4610 },
      ],
    },
    week: {
      label: "Неделя",
      metrics: { orders: 1486, turnover: 1248370, active: 23, averageCheck: 840, cancelled: 47, tasks: 31, storesOpen: 3 },
      trend: [62, 74, 69, 88, 94, 100, 81, 76],
      statuses: [{ label: "Новые", value: 5, tone: "amber" }, { label: "Ожидают кухню", value: 4, tone: "warning" }, { label: "Готовятся", value: 9, tone: "amber" }, { label: "Готовы к выдаче", value: 5, tone: "success" }],
      stores: [
        { pointId: 1, orders: 551, turnover: 469240, employees: 8, tasks: 12, deliveryOrders: 165, deliveryTurnover: 142120 },
        { pointId: 2, orders: 443, turnover: 367190, employees: 6, tasks: 11, deliveryOrders: 0, deliveryTurnover: 0 },
        { pointId: 3, orders: 346, turnover: 294100, employees: 5, tasks: 8, deliveryOrders: 121, deliveryTurnover: 104340 },
        { pointId: 4, orders: 146, turnover: 117840, employees: 3, tasks: 0, deliveryOrders: 39, deliveryTurnover: 31960 },
      ],
    },
    month: {
      label: "Месяц",
      metrics: { orders: 6248, turnover: 5284120, active: 28, averageCheck: 846, cancelled: 186, tasks: 68, storesOpen: 3 },
      trend: [58, 76, 68, 82, 98, 86, 100, 93],
      statuses: [{ label: "Новые", value: 6, tone: "amber" }, { label: "Ожидают кухню", value: 5, tone: "warning" }, { label: "Готовятся", value: 11, tone: "amber" }, { label: "Готовы к выдаче", value: 6, tone: "success" }],
      stores: [
        { pointId: 1, orders: 2321, turnover: 1984660, employees: 8, tasks: 25, deliveryOrders: 695, deliveryTurnover: 593340 },
        { pointId: 2, orders: 1854, turnover: 1568430, employees: 6, tasks: 23, deliveryOrders: 0, deliveryTurnover: 0 },
        { pointId: 3, orders: 1451, turnover: 1228080, employees: 5, tasks: 20, deliveryOrders: 512, deliveryTurnover: 436010 },
        { pointId: 4, orders: 622, turnover: 502950, employees: 3, tasks: 0, deliveryOrders: 168, deliveryTurnover: 142410 },
      ],
    },
  };

  window.SHAVERMA_BUSINESS_DEMO = { points, periods };
})();
