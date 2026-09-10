import { spawn } from "node:child_process";

import electronPath from "electron";

const environment = { ...process.env };
delete environment.ELECTRON_RUN_AS_NODE;

const desktop = spawn(electronPath, ["."], {
  cwd: process.cwd(),
  env: environment,
  stdio: "inherit",
});

desktop.on("exit", (code) => {
  process.exitCode = code ?? 1;
});
