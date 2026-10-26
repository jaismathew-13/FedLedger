// Compile only the onboarding contract, leaving historical FL artifacts unchanged.
const fs = require('node:fs');
const path = require('node:path');
const solc = require('solc');
const name = 'HospitalDirectory';
const input = {
  language: 'Solidity',
  sources: { [name + '.sol']: { content: fs.readFileSync(path.join(__dirname, 'contracts', name + '.sol'), 'utf8') } },
  settings: { evmVersion: 'shanghai', optimizer: { enabled: true, runs: 200 },
    outputSelection: { '*': { '*': ['abi', 'evm.bytecode.object'] } } }
};
const output = JSON.parse(solc.compile(JSON.stringify(input)));
for (const error of output.errors || []) console.error(error.formattedMessage);
if ((output.errors || []).some(error => error.severity === 'error')) process.exit(1);
const contract = output.contracts[name + '.sol'][name];
fs.mkdirSync(path.join(__dirname, 'artifacts'), { recursive: true });
fs.writeFileSync(path.join(__dirname, 'artifacts', name + '.json'), JSON.stringify({
  contractName: name, compiler: solc.version(), settings: input.settings,
  abi: contract.abi, bytecode: '0x' + contract.evm.bytecode.object
}, null, 2));
console.log('Saved artifacts/' + name + '.json');
