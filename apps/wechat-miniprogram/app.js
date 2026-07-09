const surfaceContract = require("./contracts/a3-client-surface.contract.js");

App({
  globalData: {
    surfaceContract,
    apiBasePath: "/api/a3",
    tokenPersistence: "disabled"
  }
});
