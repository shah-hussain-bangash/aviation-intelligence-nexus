import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {X509Certificate,createPrivateKey} from 'node:crypto';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');

export function privateTlsDirectory(value){
  if(typeof value!=='string'||!value||/[\x00-\x1f]/.test(value)||value.split(/[\\/]/).includes('..'))throw new Error('Invalid local TLS directory.');
  const target=path.resolve(root,value),base=path.join(root,'.local');
  if(!target.startsWith(base+path.sep))throw new Error('Invalid local TLS directory.');
  return target;
}

function readMaterial(directory,name,limit){
  const target=path.join(directory,name);
  for(let current=target;;current=path.dirname(current)){
    if(fs.lstatSync(current).isSymbolicLink())throw new Error();
    if(current===path.dirname(current))break;
  }
  const info=fs.statSync(target);
  if(!info.isFile()||info.size<1||info.size>limit)throw new Error();
  return fs.readFileSync(target);
}

export function localHttpsOptions(directory,pin){
  try{
    if(!/^[a-f0-9]{64}$/.test(pin))throw new Error();
    const target=privateTlsDirectory(directory),cert=readMaterial(target,'certificate.pem',64000),key=readMaterial(target,'private-key.pem',16000);
    const certificate=new X509Certificate(cert),privateKey=createPrivateKey(key),now=Date.now();
    if(certificate.fingerprint256.replaceAll(':','').toLowerCase()!==pin||certificate.toString()!==cert.toString('ascii'))throw new Error();
    if(privateKey.export({type:'pkcs8',format:'pem'})!==key.toString('ascii')||privateKey.asymmetricKeyType!=='rsa'||privateKey.asymmetricKeyDetails.modulusLength<2048)throw new Error();
    if(!certificate.checkPrivateKey(privateKey)||certificate.issuer!==certificate.subject||!certificate.verify(certificate.publicKey)||certificate.ca)throw new Error();
    const start=Date.parse(certificate.validFrom),end=Date.parse(certificate.validTo);
    if(!Number.isFinite(start)||!Number.isFinite(end)||now<start||now>=end||end-start>7*86400000+60000)throw new Error();
    if(certificate.subjectAltName!=='DNS:localhost, IP Address:127.0.0.1'||certificate.keyUsage?.join(',')!=='1.3.6.1.5.5.7.3.1')throw new Error();
    return {cert,key,minVersion:'TLSv1.2'};
  }catch{throw new Error('Local HTTPS material rejected.');}
}
