require("@nomiclabs/hardhat-ethers");
require("@nomiclabs/hardhat-etherscan");
require("dotenv").config();

const RPC_URL = process.env.RPC_URL || "https://eth.public.zkevm-test.net:8545";
const BLOCK_NUMBER = process.env.BLOCK_NUMBER ? parseInt(process.env.BLOCK_NUMBER) : undefined;

module.exports = {
  solidity: {
    version: "0.5.16",
    settings: {
      optimizer: {
        enabled: true,
        runs: 999999,
      },
    },
  },
  networks: {
    hardhat: {
      forking: {
        enabled: true,
        url: RPC_URL,
        blockNumber: BLOCK_NUMBER,
      },
      allowUnlimitedContractSize: true,
      loggingEnabled: false,
    },
  },
  mocha: {
    timeout: 200000,
  },
};
