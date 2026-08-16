# V1.6 — PPO Long-only Allocation with Cash

V1.6 adds a dependency-light reference PPO allocator after the V1.5 executable baseline. Its role
is to validate the RL research and audit pipeline before introducing larger neural networks.

## Policy contract

- The actor is a linear Gaussian policy over latent allocation logits.
- Softmax maps latent logits to non-negative asset and cash weights that sum to one.
- The final action element always represents cash; shorting and leverage are impossible.
- Training samples the Gaussian policy with an explicit seed; validation uses deterministic means.
- The critic is linear and is trained only on the declared training window.

## PPO contract

- Advantages use generalized advantage estimation with explicit `gamma` and `gae_lambda`.
- Updates use the PPO clipped probability-ratio surrogate.
- Actor, critic, exploration scale, entropy coefficient, update epochs, learning rates, clip epsilon,
  seed, and gradient norm are immutable trial inputs.
- This version intentionally uses full-batch gradient updates and a linear policy for auditability.

## Environment and reward contract

- State availability must be strictly earlier than execution.
- Forward-return windows must follow execution and cannot overlap.
- Portfolio actions contain long-only risky weights plus cash.
- Commission and slippage are deducted from gross return using actually changed risky weights.
- Reward is net log return minus optional turnover and drawdown penalties.
- Each step reports weights, cash, gross/net returns, turnover, cost, drawdown, reward, and NAV.

## Training and validation integrity

1. The state normalizer is fitted on training observations only.
2. Training and validation windows must be non-overlapping and match report lineage exactly.
3. Validation freezes the policy and normalizer and uses no stochastic sampling.
4. Validation may select a registered trial; the final test cannot tune policy or reward settings.
5. The report records the snapshot, experiment, trial, code version, windows, seed, configurations,
   normalizer, training curve, frozen validation evidence, policy parameters, and policy hash.

## Deliberate limitations

- The linear policy is a reference implementation, not a claim that PPO beats the Top-K baseline.
- V1.6 uses linear commission and slippage costs. Capacity and market-impact stress testing remains
  available in the V1.5 baseline and should be applied during comparative evaluation.
- Costs reduce NAV and reward directly; V1.6 keeps post-return weights on a gross drift basis rather
  than modeling exchange-level cash settlement.
- Statistical promotion still requires the V1.3/V1.4 CPCV, DSR, PBO, and falsification gates.
