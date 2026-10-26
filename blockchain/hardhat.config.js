import { defineConfig } from "hardhat/config";

export default defineConfig({
  solidity: "0.8.30",
  networks: {
    node: {
      type: "edr-simulated",
      chainType: "l1",
      chainId: 31337,
      hardfork: "shanghai"
    },
    localhost: {
      type: "http",
      chainType: "l1",
      chainId: 31337,
      url: "http://127.0.0.1:8545"
    }
  }
});
