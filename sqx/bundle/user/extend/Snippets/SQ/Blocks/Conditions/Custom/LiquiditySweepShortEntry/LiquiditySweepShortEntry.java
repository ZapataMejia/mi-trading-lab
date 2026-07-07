/*
 * Condicion Short — AlgoWizard Sell short entry.
 * Requiere LiquiditySweep.java compilado antes.
 */
package SQ.Blocks.Conditions.Custom;

import SQ.Blocks.Indicators.Custom.LiquiditySweep;
import SQ.Internal.ConditionBlock;

import com.strategyquant.lib.*;
import com.strategyquant.datalib.*;
import com.strategyquant.tradinglib.*;

@BuildingBlock(name="Liquidity Sweep Short Entry", display="LiqSweep Short Entry (lb#LookbackBars#)", returnType = ReturnTypes.Boolean)
@Help("True cuando LiquiditySweep dispara senal short (sweep high + reclaim en sesion).")
@ParameterSet(set="LookbackBars=36,RiskPct=1.5,TPRatio=1.5,SlBufferPips=3,MaxTradesPerDay=1,SessStart=700,SessEnd=1400")
public class LiquiditySweepShortEntry extends ConditionBlock {

	@Parameter
	public ChartData Input;

	@Parameter(defaultValue="36", minValue=6, maxValue=120, step=1)
	public int LookbackBars;

	@Parameter(defaultValue="1.5", minValue=0.5, maxValue=10, step=0.1)
	public double RiskPct;

	@Parameter(defaultValue="1.5", minValue=0.5, maxValue=5, step=0.1)
	public double TPRatio;

	@Parameter(defaultValue="3", minValue=0, maxValue=20, step=0.5)
	public double SlBufferPips;

	@Parameter(defaultValue="700", minValue=0, maxValue=2359, step=5)
	public int SessStart;

	@Parameter(defaultValue="1400", minValue=0, maxValue=2359, step=5)
	public int SessEnd;

	@Parameter(defaultValue="1", minValue=1, maxValue=10, step=1)
	public int MaxTradesPerDay;

	@Override
	public boolean OnBlockEvaluate() throws TradingException {
		LiquiditySweep ind = Strategy.Indicators.LiquiditySweep(
			Input, LookbackBars, RiskPct, TPRatio, SlBufferPips,
			SessStart, SessEnd, MaxTradesPerDay, true, true);
		return ind.ShortEntry.get(0) > 0;
	}
}
