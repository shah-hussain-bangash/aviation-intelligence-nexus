import fs from 'node:fs';
import {verifyReview} from '../apps/web/scoped-review-contract.mjs';
try{
 if(process.argv.length!==3)throw Error('Expected one review JSON path');
 const target=process.argv[2],info=fs.lstatSync(target);
 if(info.isSymbolicLink()||!info.isFile()||info.size>256*1024)throw Error('Use a regular review JSON file no larger than 256 KiB');
 const result=await verifyReview(JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(fs.readFileSync(target))));process.stdout.write(JSON.stringify(result)+'\n');
}catch{process.stderr.write('Review could not be verified. Use an unchanged exported self-review JSON file.\n');process.exitCode=1;}
