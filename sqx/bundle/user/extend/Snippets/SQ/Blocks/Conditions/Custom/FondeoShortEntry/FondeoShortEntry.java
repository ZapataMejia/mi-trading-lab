/*
 * Condicion Short — usar en AlgoWizard pestaña Short entry.
 * Requiere FondeoEMAcross.java compilado antes.
 */
package SQ.Blocks.Conditions.Custom;

import SQ.Blocks.Indicators.Custom.FondeoEMAcross;
import SQ.Internal.ConditionBlock;

import com.strategyquant.lib.*;
import com.strategyquant.datalib.*;
import com.strategyquant.tradinglib.*;

@BuildingBlock(name="Fondeo Short Entry", display="Fondeo Short Entry (EMA cross)", returnType = ReturnTypes.Boolean)
@Help("True cuando FondeoEMAcross dispara senal short (cruce bajista en sesion).")
public class FondeoShortEntry extends ConditionBlock {

	@Parameter
	public ChartData Input;

	@Parameter(defaultValue="9", minValue=2, maxValue=50, step=1)
	public int FastPeriod;

	@Parameter(defaultValue="20", minValue=3, maxValue=200, step=1)
	public int SlowPeriod;

	@Parameter(defaultValue="2.1", minValue=0.5, maxValue=10, step=0.1)
	public double RiskPct;

	@Parameter(defaultValue="1.0", minValue=0.5, maxValue=5, step=0.1)
	public double TPRatio;

	@Parameter(defaultValue="800", minValue=0, maxValue=2359, step=5)
	public int SessStart;

	@Parameter(defaultValue="1000", minValue=0, maxValue=2359, step=5)
	public int SessEnd;

	@Parameter(defaultValue="2", minValue=1, maxValue=10, step=1)
	public int MaxTradesPerDay;

	@Override
	public boolean OnBlockEvaluate() throws TradingException {
		FondeoEMAcross ind = Strategy.Indicators.FondeoEMAcross(
			Input, FastPeriod, SlowPeriod, RiskPct, TPRatio, SessStart, SessEnd, MaxTradesPerDay);
		return ind.ShortEntry.get(0) > 0;
	}
}
