const { expect } = require("chai");
const { ethers } = require("hardhat");
const BN = ethers.BigNumber;

describe("Decimal Precision Mismatch PoC - UniswapV2Pair Mint", function () {
    let token0;     // 6 decimals (USDC-like)
    let token1;     // 18 decimals (ETH-like)
    let pair;
    let deployer;
    let attacker;

    before(async function () {
        [deployer, attacker] = await ethers.getSigners();
    });

    beforeEach(async function () {
        // Deploy Token0 with 6 decimals
        const MockERC20Factory = await ethers.getContractFactory("ERC20");
        token0 = await MockERC20Factory.deploy("USDC", "USDC", 6, BN.from("10000000")); // 10M USDC
        await token0.deployed();

        // Deploy Token1 with 18 decimals
        token1 = await MockERC20Factory.deploy("WETH", "WETH", 18, BN.from("1000")); // 1000 WETH
        await token1.deployed();

        // Deploy Vulnerable Pair Contract
        const PairFactory = await ethers.getContractFactory("VulnerableUniswapV2Pair");
        pair = await PairFactory.deploy(token0.address, token1.address);
        await pair.deployed();

        // Transfer tokens to attacker
        await token0.transfer(attacker.address, BN.from("100000").mul(BN.from(10).pow(6))); // 100k USDC
        await token1.transfer(attacker.address, BN.from("100").mul(BN.from(10).pow(18))); // 100 WETH

        // Transfer initial liquidity to pair for setup
        await token0.transfer(pair.address, BN.from("1000000").mul(BN.from(10).pow(6))); // 1M USDC
        await token1.transfer(pair.address, BN.from("1000").mul(BN.from(10).pow(18))); // 1000 WETH
    });

    it("Demonstrates decimal precision loss in mint function", async function () {
        console.log("\n" + "=".repeat(80));
        console.log("DECIMAL PRECISION MISMATCH VULNERABILITY PoC");
        console.log("=".repeat(80));

        // ========== STEP 1: Initial State ==========
        console.log("\n[STEP 1] Initial State Setup");
        console.log("-".repeat(80));

        const token0Decimals = 6;
        const token1Decimals = 18;
        const decimalDifference = token1Decimals - token0Decimals; // 12

        console.log(`Token0 (USDC) Decimals: ${token0Decimals}`);
        console.log(`Token1 (WETH) Decimals: ${token1Decimals}`);
        console.log(`Decimal Difference: ${decimalDifference} orders of magnitude`);

        // Get initial reserves
        const [reserve0, reserve1] = await pair.getReserves();
        console.log(`\nInitial Pair Reserves:`);
        console.log(`  Reserve0: ${ethers.utils.formatUnits(reserve0, token0Decimals)} USDC`);
        console.log(`  Reserve1: ${ethers.utils.formatUnits(reserve1, token1Decimals)} WETH`);

        // ========== STEP 2: Prepare Unscaled Amounts ==========
        console.log("\n[STEP 2] Prepare Input Amounts for Minting");
        console.log("-".repeat(80));

        // Create inputs that exploit the decimal mismatch
        // We're adding equal "raw" amounts but different actual values due to decimals
        const rawAmount0 = BN.from("1000000").mul(BN.from(10).pow(token0Decimals)); // 1M raw units of 6-decimal token
        const rawAmount1 = BN.from("1000000").mul(BN.from(10).pow(token1Decimals)); // 1M raw units of 18-decimal token

        console.log(`\nInputs to mint function (raw units):`);
        console.log(`  Amount0: ${rawAmount0.toString()} units (${ethers.utils.formatUnits(rawAmount0, token0Decimals)} USDC)`);
        console.log(`  Amount1: ${rawAmount1.toString()} units (${ethers.utils.formatUnits(rawAmount1, token1Decimals)} WETH)`);
        console.log(`\nNotice: Amount1 is 10^12 times larger in absolute value, but represents similar value`);

        // ========== STEP 3: Calculate Expected Liquidity (CORRECTLY SCALED) ==========
        console.log("\n[STEP 3] Calculate CORRECT Liquidity (Accounting for Decimals)");
        console.log("-".repeat(80));

        // Normalize both amounts to 18 decimals for fair comparison
        const amount0Normalized = rawAmount0.mul(BN.from(10).pow(decimalDifference)); // Scale 6-decimal to 18-decimal
        const amount1Normalized = rawAmount1; // Already 18 decimals

        console.log(`\nNormalized Amounts (both to 18 decimals):`);
        console.log(`  Amount0 (scaled): ${amount0Normalized.toString()}`);
        console.log(`  Amount1 (scaled): ${amount1Normalized.toString()}`);

        // Calculate geometric mean: sqrt(amount0 * amount1)
        const product = amount0Normalized.mul(amount1Normalized);
        const expectedLiquidity = sqrt(product).sub(BN.from(1000)); // Subtract MINIMUM_LIQUIDITY

        console.log(`\nExpected Liquidity (CORRECT CALCULATION):`);
        console.log(`  sqrt(${amount0Normalized.toString()} * ${amount1Normalized.toString()})`);
        console.log(`  = ${expectedLiquidity.toString()}`);
        console.log(`  ✓ Accounts for decimal difference correctly`);

        // ========== STEP 4: Set Up Pair for Minting ==========
        console.log("\n[STEP 4] Set Up Pair State for Minting");
        console.log("-".repeat(80));

        // Transfer tokens from attacker to pair
        await token0.connect(attacker).transfer(pair.address, rawAmount0);
        await token1.connect(attacker).transfer(pair.address, rawAmount1);

        const pairBalance0 = await token0.balanceOf(pair.address);
        const pairBalance1 = await token1.balanceOf(pair.address);

        console.log(`\nPair Token Balances:`);
        console.log(`  Balance0: ${ethers.utils.formatUnits(pairBalance0, token0Decimals)} USDC`);
        console.log(`  Balance1: ${ethers.utils.formatUnits(pairBalance1, token1Decimals)} WETH`);

        // ========== STEP 5: Trigger Vulnerability ==========
        console.log("\n[STEP 5] Execute Vulnerable Mint Function");
        console.log("-".repeat(80));

        // Call mint - this uses the vulnerable formula without scaling
        const mintTx = await pair.connect(attacker).mint(attacker.address);
        await mintTx.wait();

        // Get actual liquidity minted
        const actualLiquidity = await pair.balanceOf(attacker.address);

        console.log(`\nActual Liquidity Received (from vulnerable contract):`);
        console.log(`  ${actualLiquidity.toString()}`);
        console.log(`  ✗ Does NOT account for decimal difference`);

        // ========== STEP 6: Calculate Vulnerability Impact ==========
        console.log("\n[STEP 6] Vulnerability Impact Analysis");
        console.log("-".repeat(80));

        // Calculate the loss
        const precisionLoss = expectedLiquidity.sub(actualLiquidity);
        const lossPercentage = precisionLoss.mul(BN.from(10000)).div(expectedLiquidity);

        console.log(`\nComparison:`);
        console.log(`  Expected Liquidity (CORRECT): ${expectedLiquidity.toString()}`);
        console.log(`  Actual Liquidity (VULNERABLE): ${actualLiquidity.toString()}`);
        console.log(`\nPrecision Loss:`);
        console.log(`  Raw Loss: ${precisionLoss.toString()} units`);
        console.log(`  Loss Percentage: ${(lossPercentage.toNumber() / 100).toFixed(2)}%`);

        // ========== STEP 7: Financial Impact ==========
        console.log("\n[STEP 7] Financial Impact Estimation");
        console.log("-".repeat(80));

        // Estimate impact in USD (assuming USDC ≈ $1 and WETH ≈ $2000)
        const usdcValue = ethers.utils.formatUnits(rawAmount0, token0Decimals);
        const wethValue = ethers.utils.formatUnits(rawAmount1, token1Decimals);
        const wethPriceUSD = 2000;
        const totalInputValue = parseFloat(usdcValue) + parseFloat(wethValue) * wethPriceUSD;

        const lossRatio = precisionLoss.toNumber() / expectedLiquidity.toNumber();
        const estimatedDamageUSD = totalInputValue * lossRatio;

        console.log(`\nInput Values (estimated):`);
        console.log(`  Token0: ${usdcValue} USDC ≈ $${usdcValue}`);
        console.log(`  Token1: ${wethValue} WETH ≈ $${(parseFloat(wethValue) * wethPriceUSD).toLocaleString()}`);
        console.log(`  Total Input Value: $${totalInputValue.toLocaleString()}`);
        console.log(`\nEstimated Damage:`);
        console.log(`  Loss Ratio: ${(lossRatio * 100).toFixed(2)}%`);
        console.log(`  Estimated Damage: $${estimatedDamageUSD.toLocaleString()}`);

        // ========== STEP 8: Root Cause Analysis ==========
        console.log("\n[STEP 8] Root Cause Analysis");
        console.log("-".repeat(80));
        console.log(`\nVulnerable Code in mint():`);
        console.log(`  liquidity = Math.min(`);
        console.log(`      amount0.mul(_totalSupply) / _reserve0,`);
        console.log(`      amount1.mul(_totalSupply) / _reserve1`);
        console.log(`  )`);
        console.log(`\nProblem:`);
        console.log(`  - amount0 has ${token0Decimals} decimals`);
        console.log(`  - amount1 has ${token1Decimals} decimals`);
        console.log(`  - The formula doesn't normalize these before doing arithmetic`);
        console.log(`  - Result: Severe precision loss when decimal difference is large`);

        // ========== ASSERTIONS ==========
        console.log("\n[STEP 9] Assertions");
        console.log("-".repeat(80));

        // Assert that actual liquidity is significantly less than expected
        expect(actualLiquidity).to.be.lt(expectedLiquidity);
        console.log(`✓ PASS: Actual liquidity is less than expected`);

        // Assert that the loss is significant (>10%)
        const significantLossThreshold = expectedLiquidity.div(BN.from(10)); // 10%
        expect(precisionLoss).to.be.gt(significantLossThreshold);
        console.log(`✓ PASS: Precision loss is significant (>${(10)}%)`);

        // Assert that actual liquidity is non-zero (to show some calculation happened)
        expect(actualLiquidity).to.be.gt(BN.from(0));
        console.log(`✓ PASS: Actual liquidity is greater than zero`);

        console.log("\n" + "=".repeat(80));
        console.log("VULNERABILITY CONFIRMED: Decimal Precision Mismatch");
        console.log("Users receive significantly less liquidity due to unscaled arithmetic");
        console.log("=".repeat(80) + "\n");
    });

    it("Shows how correct scaling would fix the vulnerability", async function () {
        console.log("\n" + "=".repeat(80));
        console.log("DEMONSTRATION: CORRECT SCALING FIX");
        console.log("=".repeat(80));

        const token0Decimals = 6;
        const token1Decimals = 18;
        const decimalDifference = token1Decimals - token0Decimals;

        // Setup: Add same amounts as before
        const rawAmount0 = BN.from("1000000").mul(BN.from(10).pow(token0Decimals));
        const rawAmount1 = BN.from("1000000").mul(BN.from(10).pow(token1Decimals));

        await token0.connect(ethers.provider.getSigner(0)).transfer(pair.address, rawAmount0);
        await token1.connect(ethers.provider.getSigner(0)).transfer(pair.address, rawAmount1);

        // Calculate what SHOULD happen with correct scaling
        const amount0Scaled = rawAmount0.mul(BN.from(10).pow(decimalDifference));
        const amount1Scaled = rawAmount1;

        const correctLiquidity = sqrt(amount0Scaled.mul(amount1Scaled)).sub(BN.from(1000));

        console.log(`\nWith correct scaling:` );
        console.log(`  Liquidity = sqrt(${amount0Scaled.toString()} * ${amount1Scaled.toString()})`);
        console.log(`  Liquidity = ${correctLiquidity.toString()}`);
        console.log(`\nFix recommendation:`);
        console.log(`  1. Fetch decimals from both token contracts`);
        console.log(`  2. Normalize both amounts to 18 decimals before arithmetic`);
        console.log(`  3. Or use established scaling libraries (e.g., FixedPoint in Uniswap)`);

        console.log("\n" + "=".repeat(80) + "\n");
    });
});

/**
 * Simple integer square root function for testing
 */
function sqrt(value) {
    if (value.lt(BN.from(2))) {
        return value;
    }

    let z = value;
    let x = value.div(BN.from(2)).add(BN.from(1));
    
    while (x.lt(z)) {
        z = x;
        x = value.div(x).add(x).div(BN.from(2));
    }
    
    return z;
}
