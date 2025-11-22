"""
Glider Query: Decimal Precision Mismatch Detection

This module detects arithmetic operations on token amounts that lack proper
decimal scaling, which can lead to precision loss and financial vulnerabilities
in DeFi protocols.

Key Features:
    - Identifies unscaled arithmetic in critical token functions
    - Detects missing decimal handling in multi-token operations
    - Finds hardcoded scaling without proper decimal checks

Vulnerability Pattern:
    Arithmetic operations without accounting for different token decimal values
    (e.g., 6-decimal USDC combined with 18-decimal WETH) can result in
    significant precision loss or incorrect calculations.

References:
    - EIP-20 (ERC-20): https://eips.ethereum.org/EIPS/eip-20
    - EIP-4626 (Tokenized Vault): https://eips.ethereum.org/EIPS/eip-4626
"""

from glider import *


def get_components_recursive(component):
    """
    Recursively traverse and collect all nested components.

    This function performs a depth-first traversal of an instruction or value's
    component tree, collecting all components at all levels. This is essential
    for analyzing complex expressions that may have deeply nested structures.

    Args:
        component: The instruction or value component to traverse. Must support
            the get_components() method.

    Returns:
        list: A flat list containing all discovered components at all nesting
            levels. Returns an empty list if no components exist or if an
            exception occurs during traversal.

    Note:
        - Silently handles exceptions during traversal (try/except pattern)
        - Uses breadth-first appending but depth-first recursive collection
        - Safe for circular references (though none should exist in AST)
    """
    components = []
    try:
        # Iterate through immediate child components
        for comp in component.get_components():
            # Add the component to our results
            components.append(comp)
            # Recursively collect all nested components
            components.extend(get_components_recursive(comp))
    except Exception:
        # Silently handle cases where component has no get_components method
        # or other attribute errors
        pass
    return components


def contains_arithmetic(instruction):
    """
    Detect if an instruction contains arithmetic operations.

    Scans an instruction and all its nested components for arithmetic operators.
    This is used to identify instructions performing calculations on values
    (particularly token amounts) that may need decimal scaling.

    Arithmetic Operators Detected:
        Binary: '+', '-', '*', '/', '%', '**' (add, subtract, multiply,
                divide, modulo, exponentiation)
        Assignment: '+=', '-=', '*=', '/=', '%=' (compound assignments)

    Args:
        instruction: The instruction object to analyze. Can be a simple
            instruction or a complex expression with nested components.

    Returns:
        bool: True if any arithmetic operator is found in the instruction or
            its components; False otherwise.

    Implementation Details:
        - Extracts the expression string from each component
        - Uses string matching to detect operators
        - Returns immediately on first match (short-circuit evaluation)
        - Handles exceptions gracefully for malformed components
    """
    # Define all arithmetic operators to search for (binary and compound)
    arithmetic_ops = [
        '-', '+', '/', '*', '**', '%',         # Binary operators
        '+=', '-=', '*=', '/=', '%='            # Compound assignment operators
    ]
    
    # Start with the instruction itself, then add all nested components
    components = [instruction] + get_components_recursive(instruction)

    # Iterate through all components looking for arithmetic operators
    for comp in components:
        try:
            # Extract the expression string representation
            expr = comp.expression
            # Check if any arithmetic operator exists in this expression
            if any(op in expr for op in arithmetic_ops):
                # Found an arithmetic operator - vulnerability potential
                return True
        except Exception:
            # Silently skip components that don't have an expression attribute
            # or other parsing errors
            pass
    
    # No arithmetic operations found
    return False


def contains_scaling_constant(instruction):
    """
    Detect if an instruction contains token decimal scaling constants.

    Identifies common patterns used to scale token amounts for decimal handling.
    The presence of scaling constants suggests the developer is aware of
    decimal scaling issues and may have addressed them appropriately.

    Recognized Scaling Patterns:
        Scientific notation: '1e18', '1e6', '1e8' (base 10 exponent notation)
        Exponentiation: '10**18', '10**6', '10**8' (explicit power of 10)
        Named constants: 'WAD', 'RAY', 'DECIMALS' (common scaling variable names)

    Args:
        instruction: The instruction object to scan for scaling constants.
            Can be a simple instruction or a complex expression.

    Returns:
        bool: True if any recognized scaling pattern is found in the
            instruction or its components; False otherwise.

    Implementation Details:
        - Checks all nested components recursively
        - Uses string matching for pattern detection
        - Handles parsing exceptions gracefully
        - Returns on first match (efficient)
    """
    # Define common token decimal scaling patterns and constants
    scaling_patterns = [
        '1e18', '10**18',      # Standard 18-decimal (ETH, most ERC-20)
        '1e6', '10**6',        # 6-decimal (USDC, USDT)
        '1e8', '10**8',        # 8-decimal (WBTC)
        'WAD', 'RAY',          # Maker DAO scaling constants
        'DECIMALS'             # Generic decimal constant name
    ]
    
    # Start with the instruction itself, then add all nested components
    components = [instruction] + get_components_recursive(instruction)

    # Iterate through all components looking for scaling patterns
    for comp in components:
        try:
            # Extract the expression string representation
            expr = comp.expression
            # Check if any scaling pattern exists in this expression
            if any(pattern in expr for pattern in scaling_patterns):
                # Found a scaling pattern - likely properly scaled
                return True
        except Exception:
            # Silently skip components without expression attributes
            # or other errors
            pass
    
    # No scaling patterns found
    return False


def has_zero_check_downstream(instruction):
    """
    Detect if an instruction's computed result is checked for zero/null.

    Optimized version that checks the immediate next few instructions for
    zero-checks rather than doing expensive full dataflow analysis. This
    looks for patterns like require(x > 0) immediately after the computation.

    Args:
        instruction: The arithmetic instruction to analyze.

    Returns:
        bool: True if a zero/null check is found in immediate context;
            False otherwise.

    Implementation Details:
        - Checks instruction's parent block for following instructions
        - Limits lookahead to avoid expensive analysis
        - Looks for common validation patterns
        - Handles exceptions gracefully for edge cases
    """
    try:
        # Try to get the instruction's parent block for context
        parent = instruction.parent
        if parent is None:
            return False

        # Get the function containing this instruction
        func = parent
        while func and not hasattr(func, 'instructions'):
            func = getattr(func, 'parent', None)
        
        if func is None:
            return False

        # Get all instructions in the function
        all_instrs = func.instructions().exec()
        if not all_instrs:
            return False

        # Find current instruction index
        try:
            current_idx = all_instrs.index(instruction)
        except (ValueError, TypeError):
            # Can't find this instruction in the list, bail out
            return False

        # Check the next few instructions (limit lookahead to avoid timeout)
        lookahead_limit = min(5, len(all_instrs) - current_idx - 1)
        
        for i in range(1, lookahead_limit + 1):
            next_instr = all_instrs[current_idx + i]
            
            try:
                # Check if this is a require/assert with zero-check pattern
                expr_str = next_instr.expression
                
                # Quick pattern matching for common zero checks
                if any(pattern in expr_str for pattern in [
                    '> 0', '!= 0', '>= 1',        # Common checks
                    'require(', 'assert('         # Guard patterns
                ]):
                    # Found a zero check nearby
                    return True
            except Exception:
                # Skip instructions we can't analyze
                continue

    except Exception:
        # Any error during analysis - return False conservatively
        pass

    # No zero-check found in immediate context
    return False


def scan_instructions_for_precision_issues(func, check_zero=False):
    """
    Shared helper: scan function instructions for precision vulnerabilities.

    This helper consolidates the common scanning logic used across all three
    detection strategies. It iterates through a function's instructions,
    applying consistent filters and checks for unscaled arithmetic.

    Args:
        func: The function object to scan.
        check_zero (bool): If True, skip instructions with downstream zero
            checks (used to reduce false positives). Defaults to False.

    Returns:
        list: Instructions flagged as potential precision vulnerabilities.
    """
    vulnerabilities = []
    
    # Retrieve all instructions in the function
    instructions = func.instructions().exec()

    # Analyze each instruction
    for instr in instructions:
        # Filter 1: Skip if statements (control flow, not arithmetic)
        if instr.is_if():
            continue

        # Filter 2: Get the functions being called in this instruction
        callee_names = instr.callee_names()
        
        # Filter 3: Skip guard clauses (require, assert, revert)
        # These are validation checks, not arithmetic operations
        if any(guard in callee_names for guard in [
            'require', 'assert', 'revert'
        ]):
            continue

        # Filter 4: Optional zero-check detection (reduces false positives)
        if check_zero and has_zero_check_downstream(instr):
            # This value is validated downstream, skip it
            continue

        # Core vulnerability check: arithmetic without scaling
        if (contains_arithmetic(instr) and
                not contains_scaling_constant(instr)):
            # Found potential precision vulnerability
            vulnerabilities.append(instr)

    return vulnerabilities


def query():
    """
    Execute the decimal precision mismatch detection query.

    This is the main entry point for the Glider vulnerability detection system.
    It implements three complementary strategies to identify arithmetic
    operations that may not properly handle token decimals, which can lead to
    precision loss or incorrect calculations in DeFi protocols.

    Query Metadata:
        @title: Decimal Precision Mismatches in Token Calculations 
                (ERC20/ERC4626 & DeFi)
        @description: Detects arithmetic operations on token amounts without
                     decimal scaling.
        @author: HackerDemy Team
        @tags: decimals, precision-loss, DeFi, ERC20
        @references: 
            - https://eips.ethereum.org/EIPS/eip-20 (ERC-20 Standard)
            - https://eips.ethereum.org/EIPS/eip-4626 (Tokenized Vault Standard)

    Detection Strategies:
        1. **Critical Function Analysis**: Scans common token operation functions
           (deposit, mint, swap, etc.) for unscaled arithmetic. Functions that
           call decimals() are excluded (they likely handle scaling).

        2. **Multi-Token Swap Analysis**: Identifies swap functions that may
           involve multiple tokens. Flags arithmetic without adequate decimals
           calls (requires < 2 calls).

        3. **Hardcoded Scaling Detection**: Finds instructions with hardcoded
           scaling constants (1e18, 10**6, etc.) but no decimals() calls,
           indicating potential decimal mismatches.

    Returns:
        list: Up to 100 unique instruction objects representing potential
            decimal precision vulnerabilities. Each instruction is deduplicated
            by expression text to avoid reporting the same issue multiple times.

    Process Flow:
        1. Execute three independent detection strategies
        2. Accumulate results from all strategies
        3. Deduplicate results by expression content
        4. Return top 100 results for review
    """
    # Initialize the results list to accumulate findings
    results = []

    # =========================================================================
    # STRATEGY 1: Unscaled Arithmetic in Critical Token Functions
    # =========================================================================
    # These are functions commonly used in token operations that should
    # properly handle decimal scaling
    target_functions = [
        'deposit',             # Vault/liquidity deposit operations
        'mint',                # Token/liquidity minting
        'swap',                # Token swaps (may involve multiple decimals)
        'borrow',              # Lending protocol borrowing
        'redeem',              # Vault/liquidity redemption
        'withdraw',            # Withdrawal operations
        'transfer',            # Token transfers
        'convertToShares',     # ERC-4626 vault operations
        'convertToAssets'      # ERC-4626 vault operations
    ]

    # Scan each critical function for precision vulnerabilities
    for func_name in target_functions:
        # Retrieve all functions with this name (case-insensitive, up to 100)
        funcs = Functions().with_name(func_name, sensitivity=False).exec(100)

        # Analyze each matching function
        for func in funcs:
            # Filter 1: Skip functions that already handle decimals
            # If the function explicitly calls decimals(), it's likely aware
            # of decimal scaling and may handle it correctly
            decimals_calls = func.instructions().with_callee_name(
                'decimals'
            ).exec()
            if len(decimals_calls) > 0:
                # This function calls decimals() - likely handles scaling
                continue

            # Use shared helper to scan instructions (with zero-check filtering)
            vulns = scan_instructions_for_precision_issues(func, check_zero=True)
            results.extend(vulns)

    # =========================================================================
    # STRATEGY 2: Multi-Token Swap Function Analysis
    # =========================================================================
    # Swap functions are high-risk because they often involve two tokens
    # with potentially different decimals. Using case-insensitive regex.
    swap_functions = Functions().with_name_regex(
        "[Ss][Ww][Aa][Pp]"
    ).exec(100)

    # Analyze each swap function
    for func in swap_functions:
        # Filter 1: Count how many times decimals() is called
        # Swap functions should call decimals() at least twice (once per token)
        # If they call it < 2 times, they may not handle both decimals
        decimals_calls = func.instructions().with_callee_name(
            'decimals'
        ).exec()
        
        # If decimals is called 2+ times, assume proper handling
        if len(decimals_calls) >= 2:
            continue

        # Use shared helper to scan instructions (with zero-check filtering)
        vulns = scan_instructions_for_precision_issues(func, check_zero=True)
        results.extend(vulns)

    # =========================================================================
    # STRATEGY 3: Hardcoded Scaling Without Proper Decimals Checking
    # =========================================================================
    # This strategy finds a different type of issue: hardcoded scaling
    # constants without runtime decimal verification. Example: a contract
    # hardcodes 1e18 scaling but fails with 6-decimal tokens.
    all_functions = Functions().exec(100)

    # Analyze each function in the codebase
    for func in all_functions:
        # Filter 1: Skip if function calls decimals()
        # Functions that check decimals at runtime are likely safer
        decimals_calls = func.instructions().with_callee_name(
            'decimals'
        ).exec()
        if len(decimals_calls) > 0:
            # This function checks decimals dynamically
            continue

        # Retrieve all instructions in the function
        instructions = func.instructions().exec()

        # Check each instruction
        for instr in instructions:
            # Skip if statements
            if instr.is_if():
                continue

            # Get the functions being called
            callee_names = instr.callee_names()
            
            # Skip guard clauses
            if any(guard in callee_names for guard in [
                'require', 'assert', 'revert'
            ]):
                continue

            # Core logic: has arithmetic AND hardcoded scaling (suspicious)
            # This suggests hardcoded decimal assumptions without runtime
            # verification. This fails when token decimals differ from
            # the hardcoded assumption (e.g., assuming 1e18 but receiving 1e6)
            # Note: Skip zero-check here since hardcoded scaling is rare
            # and already a strong signal of vulnerability
            if (contains_arithmetic(instr) and
                    contains_scaling_constant(instr)):
                # Found hardcoded scaling without decimal checks
                results.append(instr)

    # =========================================================================
    # DEDUPLICATION PHASE
    # =========================================================================
    # Multiple strategies may find the same instruction, so we deduplicate
    # by the instruction's expression content
    unique_results = []
    seen = set()

    # Process each result for deduplication
    for result in results:
        try:
            # Try to use the expression as the unique key
            unique_key = result.expression
        except Exception:
            # Fall back to source code string if expression fails
            unique_key = result.source_code()

        # Check if we've already seen this instruction
        if unique_key not in seen:
            # New unique instruction - add it to our results
            seen.add(unique_key)
            unique_results.append(result)

    # Return top 100 results (many will be deduplicated to fewer)
    return unique_results[:100]