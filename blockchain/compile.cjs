const fs = require('node:fs');
const path = require('node:path');
const solc = require('solc');
const names = ['ModelRegistry', 'FederatedProtocolRegistry'];
fs.mkdirSync(path.join(__dirname, 'artifacts'), { recursive: true });
for (const name of names) {
const input = {
  language: 'Solidity',
  sources: { [name + '.sol']: {
    content: fs.readFileSync(path.join(__dirname, 'contracts', name + '.sol'), 'utf8')
  } },
  settings: {
    evmVersion: 'shanghai', // Match the configured Hardhat development hardfork.
    optimizer: { enabled: true, runs: 200 },
    ...(name === 'FederatedProtocolRegistry' ? { viaIR: true } : {}),
    outputSelection: { '*': { '*': ['abi', 'evm.bytecode.object'] } }
  }
};
const output = JSON.parse(solc.compile(JSON.stringify(input)));
for (const diagnostic of output.errors || []) console.error(diagnostic.formattedMessage);
if ((output.errors || []).some(item => item.severity === 'error')) process.exit(1);
  const contract = output.contracts[name + '.sol'][name];
  fs.writeFileSync(path.join(__dirname, 'artifacts', name + '.json'), JSON.stringify({
    contractName: name, compiler: solc.version(), settings: input.settings,
    abi: contract.abi, bytecode: '0x' + contract.evm.bytecode.object
  }, null, 2));
  console.log('Saved artifacts/' + name + '.json');
}
