using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Verge.Trading.DecisionEngine.Factory;
using Verge.Trading.DecisionEngine.Profiles;
using Volo.Abp.Domain.Services;

namespace Verge.Trading.DecisionEngine;

public class TradingDecisionEngine : DomainService, ITradingDecisionEngine
{
    private readonly ILogger<TradingDecisionEngine> _logger;
    private readonly IProbabilisticEngine _probabilisticEngine;
    private readonly Volo.Abp.Domain.Repositories.IRepository<StrategyCalibration, Guid> _calibrationRepository;
    private readonly IWhaleTrackerService _whaleTrackerService;
    private readonly IInstitutionalDataService _institutionalDataService;
    private readonly IMacroSentimentService _macroSentimentService;

    public TradingDecisionEngine(
        ILogger<TradingDecisionEngine> logger,
        IProbabilisticEngine probabilisticEngine,
        Volo.Abp.Domain.Repositories.IRepository<StrategyCalibration, Guid> calibrationRepository,
        IWhaleTrackerService whaleTrackerService,
        IInstitutionalDataService institutionalDataService,
        IMacroSentimentService macroSentimentService)
    {
        _logger = logger;
        _probabilisticEngine = probabilisticEngine;
        _calibrationRepository = calibrationRepository;
        _whaleTrackerService = whaleTrackerService;
        _institutionalDataService = institutionalDataService;
        _macroSentimentService = macroSentimentService;
    }

    public async Task<DecisionResult> EvaluateAsync(
        TradingSession session, 
        TradingStyle style, 
        MarketContext context, 
        bool isAutoMode = false,
        Dictionary<string, float>? weightOverrides = null,
        int? entryThresholdOverride = null,
        float? trailingMultiplierOverride = null)
    {
        _logger.LogInformation("🧠 Profile-Based Evaluation: Session {SessionId} | Style: {Style} | AutoAdapt: {AutoAdapt}", session.Id, style, isAutoMode);

        // 0. Update Direction based on Market Structure (Sprint 2 Adaptive)
        if (isAutoMode)
        {
            UpdateDirectionBasedOnStructure(session, context);
        }

        // 1. Get corresponding Profile
        var profile = TradingStyleProfileFactory.GetProfile(style);

        // 2. Setup Invalidation Check (Phase 2)
        if (session.CurrentStage == TradingStage.Prepared)
        {
            if (profile.IsInvalidated(context, out string invalidReason))
            {
                var invalidResult = new DecisionResult
                {
                    Decision = TradingDecision.Ignore,
                    Score = 0,
                    Reason = $"⚠️ SETUP INVALIDATED: {invalidReason}"
                };
                _logger.LogWarning("❌ Session {SessionId} invalidated: {Reason}", session.Id, invalidResult.Reason);
                return invalidResult;
            }
        }
        
        // 3. Validate Market Regime
        var currentRegime = context.MarketRegime?.Regime ?? MarketRegimeType.Ranging;
        if (!profile.ValidRegimes.Contains(currentRegime))
        {
            var invalidRegimeResult = new DecisionResult
            {
                Decision = TradingDecision.Ignore,
                Score = 0,
                Reason = $"IGNORE: Invalid Regime '{currentRegime}' for {style} style."
            };
            _logger.LogInformation("✅ Evaluation Result for {Style}: {Decision} | Reason: {Reason}", style, invalidRegimeResult.Decision, invalidRegimeResult.Reason);
            return invalidRegimeResult;
        }

        // 4. Component Score Calculation (0-100)
        float technicalScore = CalculateTechnicalScore(context);
        float quantitativeScore = CalculateQuantitativeScore(context);
        float sentimentScore = CalculateSentimentScore(context);
        float fundamentalScore = CalculateFundamentalScore(context);

        // 4.1. Institutional Score Calculation (Whale Activity)
        context.WhaleData ??= await _whaleTrackerService.GetWhaleActivityAsync(session.Symbol);
        context.InstitutionalData ??= await _institutionalDataService.GetInstitutionalDataAsync(session.Symbol);
        context.MacroData ??= await _macroSentimentService.GetMacroSentimentAsync();
        
        float institutionalScore = CalculateInstitutionalScore(context);

        // 5. Apply Profile Weights (Sprint 4: Adaptive Weights + Calibration)
        var calibration = await GetCalibrationAsync(style, currentRegime);
        var weights = await GetAdaptiveWeightsAsync(currentRegime, profile, calibration, context, session, style, weightOverrides);
        
        float finalScore = (technicalScore * weights.Technical) +
                           (quantitativeScore * weights.Quantitative) +
                           (sentimentScore * weights.Sentiment) +
                           (fundamentalScore * weights.Fundamental) +
                           (institutionalScore * weights.Institutional);

        // 5.1 Apply Threshold Shift from Calibration (Fallback) or Absolute Optimized Threshold
        int thresholdShift = calibration?.EntryThresholdShift ?? 0;
        int? entryThresholdCalibrated = calibration?.EntryThreshold;
        
        // 6. Apply Profile Penalties
        finalScore = profile.ApplyPenalties(context, finalScore, out string penaltyReason);

        // 6.1 Apply Setup Decay (Institutional 1% Sprint 1)
        finalScore = ApplySetupDecay(session, profile, finalScore, ref penaltyReason);

        int roundedScore = (int)Math.Clamp(finalScore, 0, 100);

        // 3. Hard Setup Validation (Setup Validator Phase)
        if (!profile.ValidateEntry(context, out string setupInvalidReason))
        {
            var setupInvalidResult = new DecisionResult
            {
                Decision = TradingDecision.Ignore,
                Score = roundedScore, // Return the decaying score so UI tracks it smoothly
                Reason = $"IGNORE: {setupInvalidReason}"
            };

            // Always calculate SL/TP even for invalidated results so the UI has real data
            var earlyCandle = context.Candles.LastOrDefault();
            var earlyPrice = earlyCandle?.Close ?? 0;
            if (earlyPrice > 0)
            {
                var earlyDir = session.SelectedDirection;
                if (earlyDir == null || earlyDir == SignalDirection.Auto)
                    earlyDir = context.MarketRegime?.Structure == "Bearish" ? SignalDirection.Short : SignalDirection.Long;

                var earlyAtr = (decimal)(context.Technicals?.Atr ?? 0);
                var earlyRisk = earlyAtr > 0 ? earlyAtr * 1.5m : earlyPrice * 0.015m;
                var earlyRR = 2.0m;

                if (earlyDir == SignalDirection.Long)
                {
                    setupInvalidResult.StopLossPrice = earlyPrice - earlyRisk;
                    setupInvalidResult.TakeProfitPrice = earlyPrice + earlyRisk * earlyRR;
                }
                else
                {
                    setupInvalidResult.StopLossPrice = earlyPrice + earlyRisk;
                    setupInvalidResult.TakeProfitPrice = earlyPrice - earlyRisk * earlyRR;
                }

                setupInvalidResult.RiskRewardRatio = (double?)earlyRR;
                setupInvalidResult.WinProbability = 0.5f; // Neutral fallback
            }

            _logger.LogInformation("✅ Evaluation Result for {Style}: {Decision} | Reason: {Reason} | SL: {SL} | TP: {TP}", style, setupInvalidResult.Decision, setupInvalidResult.Reason, setupInvalidResult.StopLossPrice, setupInvalidResult.TakeProfitPrice);
            return setupInvalidResult;
        }

        // 7. Probabilistic Engine (Sprint 4)
        var winRate = await _probabilisticEngine.GetWinRateAsync(style, session.Symbol, currentRegime, roundedScore, DateTime.UtcNow);

        // 8. Decision Mapping based on Profile Thresholds (Sprint 4: Dynamic Thresholds)
        var thresholds = profile.GetAdjustedThresholds(winRate.Probability);
        
        // Apply calibration shifts or absolute optimized thresholds
        thresholds = (
            entryThresholdOverride ?? entryThresholdCalibrated ?? Math.Clamp(thresholds.Entry + thresholdShift, 0, 100),
            Math.Clamp(thresholds.Prepare + thresholdShift, 0, 100),
            Math.Clamp(thresholds.Context + thresholdShift, 0, 100)
        );

        var decision = GetDecisionFromThresholds(roundedScore, thresholds);
        
        // 9. Multi-Timeframe Confirmation (Phase 2)
        if (decision == TradingDecision.Entry)
        {
            if (!ValidateHTFConfirmation(context, session, style, profile, out string htfReason))
            {
                decision = TradingDecision.Prepare;
                roundedScore = Math.Min(roundedScore, profile.EntryThreshold - 1);
                penaltyReason += $" [HTF Conflict: {htfReason}]";
            }
        }

        // 8. Confidence Calculation (Phase 2)
        var confidence = CalculateConfidence(context, style);

        // 9. Temporal Persistence Check (Phase 2.1)
        if (decision == TradingDecision.Entry)
        {
            if (!CheckTemporalPersistence(session, profile, roundedScore, out string persistenceReason))
            {
                decision = TradingDecision.Prepare;
                penaltyReason += $" {persistenceReason}";
            }
        }

        // 9.1 Calculate Institutional Metrics (Sprint 1)
        var winProb = CalculateWinProbability(roundedScore, confidence, context);
        var rrRatio = CalculateRiskRewardRatio(context, style, decision);

        // 8. Add Structural Context to Reason (Sprint 2)
        if (context.MarketRegime != null && context.MarketRegime.Structure != "Neutral")
        {
            var structInfo = $"[{context.MarketRegime.Structure}";
            if (context.MarketRegime.BosDetected) structInfo += " / BOS Detected";
            if (context.MarketRegime.ChochDetected) structInfo += " / CHOCH Detected";
            structInfo += "]";
            penaltyReason = $"{structInfo} {penaltyReason}".Trim();
        }

        var result = new DecisionResult
        {
            Decision = decision,
            Score = roundedScore,
            Reason = string.IsNullOrEmpty(penaltyReason) 
                ? (decision == TradingDecision.Entry ? "🚀 ENTRY SETUP READY" : $"Score: {roundedScore}. Style: {style}.")
                : $"{penaltyReason} | WinProb: {winRate.Probability:P0} | Thresh: {thresholds.Entry}/{thresholds.Prepare}".Trim(),
            Confidence = confidence,
            WeightedScores = new Dictionary<string, float>
            {
                { "Technical", technicalScore * weights.Technical },
                { "Quantitative", quantitativeScore * weights.Quantitative },
                { "Sentiment", sentimentScore * weights.Sentiment },
                { "Fundamental", fundamentalScore * weights.Fundamental }
            },
            WinProbability = winRate.Probability, // Use Sprint 4 Engine Probability
            HistoricSampleSize = winRate.SampleSize,
            RiskRewardRatio = rrRatio,
            WhaleInfluenceScore = context.WhaleData?.MaxInfluenceDetected ?? 0,
            WhaleSentiment = context.WhaleData?.Summary,
            MacroQuietPeriod = context.MacroData?.IsInQuietPeriod ?? false,
            MacroReason = context.MacroData?.QuietPeriodReason,
            TrailingMultiplier = trailingMultiplierOverride ?? calibration?.TrailingMultiplier ?? profile.TrailingMultiplier
        };

        // 10.1 Institutional 1% Price Calculation (Sprint 1)
        var lastCandle = context.Candles.LastOrDefault();
        var currentPrice = lastCandle?.Close ?? 0;
        
        if (session.Symbol == "BTCUSDT")
        {
            _logger.LogWarning("🔍 [DEBUG BTC] Starting Price Calculation. CandleCount: {Count}, CurrentPrice: {Price}, Decision: {Decision}, SelectedDirection: {Dir}",
                context.Candles?.Count ?? 0, currentPrice, result.Decision, session.SelectedDirection?.ToString() ?? "null");
        }
        
        if (currentPrice > 0)
        {
            // Determine concrete direction for the result if session is still Auto or null
            var effectiveDirection = session.SelectedDirection;
            if (effectiveDirection == null || effectiveDirection == SignalDirection.Auto)
            {
                // Fallback to structure or momentum if still Auto/null
                effectiveDirection = context.MarketRegime?.Structure == "Bearish" ? SignalDirection.Short : SignalDirection.Long;
                session.SelectedDirection = effectiveDirection; // Persist for this session
            }

            var atr = (decimal)(context.Technicals?.Atr ?? 0);
            var riskAmount = atr > 0 ? atr * 1.5m : currentPrice * 0.015m; // 1.5x ATR or 1.5% fixed
            var rr = (decimal)result.RiskRewardRatio.GetValueOrDefault(2.0);
            if (rr <= 0) rr = 2.0m;

            if (session.Symbol == "BTCUSDT")
            {
                _logger.LogWarning("🔍 [DEBUG BTC] Params -> ATR: {Atr}, RiskAmount: {RiskAmount}, RR: {RR}, Direction: {Dir}", atr, riskAmount, rr, effectiveDirection);
            }

            if (effectiveDirection == SignalDirection.Long)
            {
                result.StopLossPrice = currentPrice - riskAmount;
                result.TakeProfitPrice = currentPrice + (riskAmount * rr);
            }
            else
            {
                result.StopLossPrice = currentPrice + riskAmount;
                result.TakeProfitPrice = currentPrice - (riskAmount * rr);
            }
            
            if (session.Symbol == "BTCUSDT")
            {
                _logger.LogWarning("🔍 [DEBUG BTC] Assigned -> SL: {SL}, TP: {TP}", result.StopLossPrice, result.TakeProfitPrice);
            }
        }

        // 9. Quiet Period Enforcement (Sprint 5)
        if (context.MacroData?.IsInQuietPeriod == true)
        {
            _logger.LogWarning("🌍 BLOCKING ENTRY: Quiet period active for {symbol} due to macroeconomic volatility.", session.Symbol);
            result.Decision = TradingDecision.Ignore;
            result.Reason = context.MacroData.QuietPeriodReason;
            
            if (session.Symbol == "BTCUSDT") _logger.LogWarning("🔍 [DEBUG BTC] Exiting early at Quiet Period. SL: {SL}, TP: {TP}", result.StopLossPrice, result.TakeProfitPrice);
            return result;
        }

        if (winRate.Probability > 0.75 && winRate.SampleSize >= 10)
        {
            result.PatternSignal = $"🔥 WINNING PATTERN: {style} in {currentRegime} with {roundedScore} score has {winRate.Probability:P0} Win Rate!";
            _logger.LogInformation("🎯 Pattern Detected for {Symbol}: {Pattern}", session.Symbol, result.PatternSignal);
        }

        // 10. Entry Range Calculation (Sprint 4)
        if (result.Decision >= TradingDecision.Prepare)
        {
            var entryBasePrice = context.Candles.Last().Close;
            // 0.5% Zone window (+-0.25%)
            result.EntryMinPrice = entryBasePrice * 0.9975m;
            result.EntryMaxPrice = entryBasePrice * 1.0025m;
        }

        if (session.Symbol == "BTCUSDT")
        {
            _logger.LogWarning("🔍 [DEBUG BTC] Returning Result -> Decision: {Decision}, SL: {SL}, TP: {TP}", result.Decision, result.StopLossPrice, result.TakeProfitPrice);
        }

        _logger.LogInformation("✅ Evaluation Result for {Style}: {Decision} (Score: {Score})", style, result.Decision, result.Score);
        return result;
    }

    private void UpdateDirectionBasedOnStructure(TradingSession session, MarketContext context)
    {
        if (context.MarketRegime == null) return;

        var structure = context.MarketRegime.Structure;
        var bos = context.MarketRegime.BosDetected;
        var choch = context.MarketRegime.ChochDetected;

        // Adaptive Direction Logic (Sprint 2)
        // If we detect a clear structural break (BOS or CHOCH), we flip the session direction
        if (structure == "Bullish" && (bos || choch))
        {
            if (session.SelectedDirection != SignalDirection.Long)
            {
                _logger.LogInformation("🔄 AUTO ADAPT: Changing direction to LONG due to {Type} detected for {Symbol} (Session: {Id})", 
                    bos ? "BOS" : "CHOCH", session.Symbol, session.Id);
                session.SelectedDirection = SignalDirection.Long;
            }
        }
        else if (structure == "Bearish" && (bos || choch))
        {
            if (session.SelectedDirection != SignalDirection.Short)
            {
                _logger.LogInformation("🔄 AUTO ADAPT: Changing direction to SHORT due to {Type} detected for {Symbol} (Session: {Id})", 
                    bos ? "BOS" : "CHOCH", session.Symbol, session.Id);
                session.SelectedDirection = SignalDirection.Short;
            }
        }
    }

    private TradingDecision GetDecisionFromThresholds(int score, (int Entry, int Prepare, int Context) thresholds)
    {
        if (score >= thresholds.Entry) return TradingDecision.Entry;
        if (score >= thresholds.Prepare) return TradingDecision.Prepare;
        if (score >= thresholds.Context) return TradingDecision.Context;
        return TradingDecision.Ignore;
    }

    private async Task<(float Technical, float Quantitative, float Sentiment, float Fundamental, float Institutional)> GetAdaptiveWeightsAsync(
        MarketRegimeType regime, 
        ITradingStyleProfile profile, 
        StrategyCalibration? calibration, 
        MarketContext context,
        TradingSession session,
        TradingStyle style,
        Dictionary<string, float>? weightOverrides = null)
    {
        // 0. Manual Overrides (Used for Optimization Phase 6)
        if (weightOverrides != null)
        {
            _logger.LogInformation("🎯 ADAPTIVE WEIGHTS: Using manual overrides for optimization.");
            float oTech = weightOverrides.GetValueOrDefault("Technical", profile.TechnicalWeight);
            float oQuant = weightOverrides.GetValueOrDefault("Quantitative", profile.QuantitativeWeight);
            float oSent = weightOverrides.GetValueOrDefault("Sentiment", profile.SentimentWeight);
            float oFund = weightOverrides.GetValueOrDefault("Fundamental", profile.FundamentalWeight);
            float oInst = weightOverrides.GetValueOrDefault("Whales", profile.InstitutionalWeight); // Mapper uses "Whales"
            
            float oTotal = oTech + oQuant + oSent + oFund + oInst;
            if (oTotal <= 0) return (0.2f, 0.2f, 0.2f, 0.2f, 0.2f);
            return (oTech / oTotal, oQuant / oTotal, oSent / oTotal, oFund / oTotal, oInst / oTotal);
        }

        // 0.1 Check for Absolute Calibrated Weights in DB
        if (calibration != null && !string.IsNullOrEmpty(calibration.WeightsJson))
        {
            try
            {
                var calWeights = System.Text.Json.JsonSerializer.Deserialize<Dictionary<string, float>>(calibration.WeightsJson);
                if (calWeights != null)
                {
                    _logger.LogInformation("🏆 ADAPTIVE WEIGHTS: Using ABSOLUTE calibrated weights from DB.");
                    float cTech = calWeights.GetValueOrDefault("Technical", profile.TechnicalWeight);
                    float cQuant = calWeights.GetValueOrDefault("Quantitative", profile.QuantitativeWeight);
                    float cSent = calWeights.GetValueOrDefault("Sentiment", profile.SentimentWeight);
                    float cFund = calWeights.GetValueOrDefault("Fundamental", profile.FundamentalWeight);
                    float cInst = calWeights.GetValueOrDefault("Whales", profile.InstitutionalWeight);

                    float cTotal = cTech + cQuant + cSent + cFund + cInst;
                    if (cTotal > 0) return (cTech / cTotal, cQuant / cTotal, cSent / cTotal, cFund / cTotal, cInst / cTotal);
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning("⚠️ Error parsing WeightsJson for calibration: {Message}", ex.Message);
            }
        }

        // 1. BASE WEIGHTS (from Profile + Calibration Multipliers)
        float technical = profile.TechnicalWeight * (calibration?.TechnicalMultiplier ?? 1.0f);
        float quantitative = profile.QuantitativeWeight * (calibration?.QuantitativeMultiplier ?? 1.0f);
        float sentiment = profile.SentimentWeight * (calibration?.SentimentMultiplier ?? 1.0f);
        float fundamental = profile.FundamentalWeight * (calibration?.FundamentalMultiplier ?? 1.0f);
        float institutional = profile.InstitutionalWeight * (calibration?.InstitutionalMultiplier ?? 1.0f);

        // 2. DYNAMIC FEEDBACK (NO MORE FIXED RULES)
        // We query the Probabilistic Engine to see which components performed better in this regime
        var perf = await _probabilisticEngine.GetWinRateAsync(style, session.Symbol, regime, 70, DateTime.UtcNow.AddDays(-7));
        
        if (perf.SampleSize >= 10)
        {
            // If we have enough data, we slightly boost weights if probability is high
            float boost = (float)(perf.Probability - 0.5) * 0.5f; // -0.25 to +0.25
            
            if (regime == MarketRegimeType.Ranging) technical += boost;
            else quantitative += boost;
            
            _logger.LogInformation("🧠 ADAPTIVE WEIGHTS: Applying dynamic boost of {Boost:F2} based on {Count} samples.", boost, perf.SampleSize);
        }

        // 3. INSTITUTIONAL SQUEEZE OVERRIDE
        if (context.InstitutionalData?.IsSqueezeDetected == true)
        {
            quantitative *= 1.5f; 
            technical *= 0.5f;
            _logger.LogInformation("🔥 ADAPTIVE WEIGHTS: Boosting institutional weight due to Squeeze detected!");
        }

        // Normalize weights to sum to 1.0
        float total = technical + quantitative + sentiment + fundamental + institutional;
        if (total <= 0) return (0.2f, 0.2f, 0.2f, 0.2f, 0.2f);
        return (technical / total, quantitative / total, sentiment / total, fundamental / total, institutional / total);
    }

    private async Task<StrategyCalibration?> GetCalibrationAsync(TradingStyle style, MarketRegimeType regime)
    {
        try
        {
            var query = await _calibrationRepository.GetQueryableAsync();
            return query.FirstOrDefault(c => c.Style == style && c.Regime == regime);
        }
        catch (Exception ex)
        {
            _logger.LogWarning("⚠️ Could not fetch StrategyCalibration: {Message}", ex.Message);
            return null;
        }
    }

    #region Component Calculations (Linear logic remains consistent for comparability)
    private float CalculateTechnicalScore(MarketContext context)
    {
        if (context.Technicals == null) return 50f;
        float score = 50f;
        
        if (context.Technicals.Rsi < 30) score += 20;
        else if (context.Technicals.Rsi > 70) score -= 20;
        
        if (context.Technicals.MacdHistogram > 0) score += 15;
        else score -= 15;
        
        return Math.Clamp(score, 0, 100);
    }

    private float CalculateQuantitativeScore(MarketContext context)
    {
        if (context.MarketRegime == null) return 50f;
        float score = 50f;
        
        score += (context.MarketRegime.TrendStrength / 2);
        
        if (context.MarketRegime.Regime == MarketRegimeType.BullTrend) score += 20;
        if (context.MarketRegime.Regime == MarketRegimeType.BearTrend) score -= 20;
        
        return Math.Clamp(score, 0, 100);
    }

    private float CalculateSentimentScore(MarketContext context)
    {
        float score = 50f;
        
        if (context.FearAndGreed != null)
        {
            if (context.FearAndGreed.Value < 20) score += 25;
            if (context.FearAndGreed.Value > 80) score -= 25;
        }

        if (context.GlobalSentiment != null)
        {
            if (context.GlobalSentiment.Label == "positive") score += 20;
            if (context.GlobalSentiment.Label == "negative") score -= 20;
        }

        return Math.Clamp(score, 0, 100);
    }

    private float CalculateFundamentalScore(MarketContext context)
    {
        return 50f; // Standardized fundamental base
    }

    private float CalculateInstitutionalScore(MarketContext context)
    {
        float score = 50f;

        // 1. Whale Activity (NetFlow + Influence)
        if (context.WhaleData != null)
        {
            score += (float)(context.WhaleData.NetFlowScore * 20); // -20 to +20
            if (context.WhaleData.MaxInfluenceDetected > 0.8)
            {
                score += context.WhaleData.NetFlowScore > 0 ? 10 : -10;
            }
        }

        // 2. Liquidation Squeezes (Sprint 5)
        if (context.InstitutionalData != null)
        {
            if (context.InstitutionalData.IsSqueezeDetected)
            {
                // A short squeeze is BULLISH (seller exhaustion), a long squeeze is BEARISH
                score += context.InstitutionalData.SqueezeType == "Short Squeeze" ? 25 : -25;
            }

            // 3. Bid/Ask Imbalance (Order Flow)
            // Ratio > 2.0 is strong. We use (Ratio - 1.0) * 10
            double imbalanceBonus = (context.InstitutionalData.BidAskImbalance - 1.0) * 10;
            score += (float)Math.Clamp(imbalanceBonus, -20, 20);
        }

        return Math.Clamp(score, 0, 100);
    }
    #endregion

    #region Phase 2: Intelligence Helpers
    private SignalConfidence CalculateConfidence(MarketContext context, TradingStyle style)
    {
        // 1. RSI Stability (Check recent variance if possible, otherwise look at ADX as proxy for trend quality)
        var adx = context.Technicals?.Adx ?? 0;
        var score = 0;

        if (adx > 30) score += 40; // High trend strength = high confidence in trend-following
        else if (adx > 20) score += 20;

        // 2. Regime Consistency
        if (context.MarketRegime != null && context.MarketRegime.TrendStrength > 60) score += 30;

        // 3. Sentiment Alignment
        if (context.GlobalSentiment?.Label == "positive" && context.MarketRegime?.Regime == MarketRegimeType.BullTrend) score += 30;
        if (context.GlobalSentiment?.Label == "negative" && context.MarketRegime?.Regime == MarketRegimeType.BearTrend) score += 30;

        if (score >= 80) return SignalConfidence.High;
        if (score >= 40) return SignalConfidence.Medium;
        return SignalConfidence.Low;
    }

    private bool CheckTemporalPersistence(TradingSession session, ITradingStyleProfile profile, int currentScore, out string reason)
    {
        reason = string.Empty;
        var requiredCount = profile.RequiredConfirmations;
        if (requiredCount <= 1) return true;

        // Persistence logic: Parse History
        var history = ParseHistory(session.EvaluationHistoryJson);
        history.Add(currentScore);
        
        // Keep last 10
        if (history.Count > 10) history = history.Skip(history.Count - 10).ToList();
        
        // Save back to session (Transiently)
        session.EvaluationHistoryJson = System.Text.Json.JsonSerializer.Serialize(history);

        // Check last N
        if (history.Count < requiredCount)
        {
            reason = $"[WAITING: Needs {requiredCount} cycles, have {history.Count}]";
            return false;
        }

        var lastN = history.TakeLast(requiredCount).ToList();
        bool allAbove = lastN.All(s => s >= profile.EntryThreshold);

        if (!allAbove)
        {
            reason = $"[CONSISTENCY: Latest sequence failed stability check]";
            return false;
        }

        return true;
    }

    #region Institutional 1% Helpers (Sprint 1)
    private float ApplySetupDecay(TradingSession session, ITradingStyleProfile profile, float currentScore, ref string reason)
    {
        // Sprint 1 Patch: Apply to both Evaluating (Context) and Prepared stages
        if (session.CurrentStage != TradingStage.Evaluating && session.CurrentStage != TradingStage.Prepared)
            return currentScore;

        // Fallback to StartTime if the session was created before the StageChangedTimestamp update
        var referenceTime = session.StageChangedTimestamp ?? session.StartTime;
        var minutesInStage = (float)(DateTime.UtcNow - referenceTime).TotalMinutes;
        
        if (minutesInStage <= 2) return currentScore; // Grace period

        // Penalty logic: 
        // Prepared: Full Decay (Act fast or lose setup)
        // Evaluating: 50% Decay (Allow for longer context discovery)
        float efficiencyFactor = session.CurrentStage == TradingStage.Evaluating ? 0.5f : 1.0f;
        float decay = minutesInStage * profile.DecayFactor * efficiencyFactor;

        reason += $" [Setup Decay ({session.CurrentStage}): -{decay:F1}]";
        
        return Math.Max(0, currentScore - decay);
    }

    private double CalculateWinProbability(int score, SignalConfidence confidence, MarketContext context)
    {
        // Base probability from score (0-100 -> 30%-60%)
        double prob = 30.0 + (score * 0.3);
        
        // Boost from confidence
        if (confidence == SignalConfidence.High) prob += 15.0;
        else if (confidence == SignalConfidence.Medium) prob += 5.0;

        // Regime alignment boost
        if (context.MarketRegime?.TrendStrength > 70) prob += 10.0;

        return Math.Min(95.0, prob) / 100.0;
    }

    private double CalculateRiskRewardRatio(MarketContext context, TradingStyle style, TradingDecision decision)
    {
        // Institutional estimation based on profile expectations
        // Scalping usually targets smaller R:R (1:1.5)
        // Swing targets larger R:R (1:3)
        return style switch
        {
            TradingStyle.Scalping => 1.5,
            TradingStyle.DayTrading => 2.0,
            TradingStyle.SwingTrading => 3.0,
            TradingStyle.PositionTrading => 4.5,
            _ => 2.0
        };
    }
    #endregion

    private bool ValidateHTFConfirmation(MarketContext context, TradingSession session, TradingStyle style, ITradingStyleProfile profile, out string reason)
    {
        reason = string.Empty;
        var htfContext = context.HigherTimeframeContext;
        if (htfContext == null) return true; // Cannot validate if not present (log as warning in monitor)

        var htfRegime = htfContext.MarketRegime?.Regime ?? MarketRegimeType.Ranging;

        // Simple Contradiction Rules
        // 1. Long on lower TF while higher TF is BearTrend
        if (htfRegime == MarketRegimeType.BearTrend && style != TradingStyle.GridTrading)
        {
            reason = $"HTF contradiction: Cannot Long while HTF is in BearTrend";
            return false;
        }

        // 2. Short on lower TF while higher TF is BullTrend
        // (Assuming session direction logic exists elsewhere or we check RSI/MACD of HTF)

        return true;
    }

    private List<int> ParseHistory(string? json)
    {
        if (string.IsNullOrEmpty(json)) return new List<int>();
        try { return System.Text.Json.JsonSerializer.Deserialize<List<int>>(json) ?? new List<int>(); }
        catch { return new List<int>(); }
    }
    #endregion
}
