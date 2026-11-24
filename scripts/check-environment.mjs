import {environmentDiagnostic} from './runtime-config.mjs';
const report=environmentDiagnostic();
console.log(JSON.stringify(report,null,2));
if(!report.valid)process.exitCode=2;
