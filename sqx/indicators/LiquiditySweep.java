/*
 * Custom Indicator: Liquidity Sweep SAFE (SMC — lab trading)
 *
 * PEGAR EN SQX: Code Editor -> New Snippet -> Indicator -> pegar -> Compile.
 *
 * AlgoWizard (2 reglas):
 *   Long:  LiquiditySweep.LongEntry  > 0  -> Enter at Market, SL=LongStop, TP=LongTP
 *   Short: LiquiditySweep.ShortEntry > 0  -> Enter at Market, SL=ShortStop, TP=ShortTP
 *
 * MM: Risk fixed 1.5% · Max 1 open trade · Max 1 trade/day (indicador).
 *
 * Config SAFE: Lookback=36, Sess 700-1400, TP 1.5, SL buffer 3 pips, Risk 1.5%.
 */
package SQ.Blocks.Indicators.Custom;

import SQ.Internal.IndicatorBlock;

import com.strategyquant.lib.*;
import com.strategyquant.datalib.*;
import com.strategyquant.tradinglib.*;

@BuildingBlock(name="Liquidity Sweep", display="LiquiditySweep(@Chart@ lb#LookbackBars#)", returnType = ReturnTypes.Price)
@Help("Sweep swing H/L + reclaim. Outputs: LongEntry/ShortEntry, LongStop/ShortStop, LongTP/ShortTP.")
@ParameterSet(set="LookbackBars=36,RiskPct=1.5,TPRatio=1.5,SlBufferPips=3,MaxTradesPerDay=1,SessStart=700,SessEnd=1400")
public class LiquiditySweep extends IndicatorBlock {

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

	@Parameter(defaultValue="true")
	public boolean AllowLong;

	@Parameter(defaultValue="true")
	public boolean AllowShort;

	@Output(name="LongEntry")
	public DataSeries LongEntry;

	@Output(name="ShortEntry")
	public DataSeries ShortEntry;

	@Output(name="LongStop")
	public DataSeries LongStop;

	@Output(name="ShortStop")
	public DataSeries ShortStop;

	@Output(name="LongTP")
	public DataSeries LongTP;

	@Output(name="ShortTP")
	public DataSeries ShortTP;

	private int barsSeen;
	private int dayKey;
	private int tradesToday;

	@Override
	protected void OnInit() throws TradingException {
		barsSeen = 0;
		dayKey = -1;
		tradesToday = 0;
	}

	private int dayKey(long barTime) {
		return SQTime.getYear(barTime) * 10000
			+ SQTime.getMonth(barTime) * 100
			+ SQTime.getDay(barTime);
	}

	private boolean inSession(long barTime) {
		int hhmm = SQTime.getHour(barTime) * 100 + SQTime.getMinute(barTime);
		return (hhmm >= SessStart && hhmm <= SessEnd);
	}

	private double pipSize() {
		return 0.0001;
	}

	private void resetOutputs() throws TradingException {
		LongEntry.set(0);
		ShortEntry.set(0);
		LongStop.set(0);
		ShortStop.set(0);
		LongTP.set(0);
		ShortTP.set(0);
	}

	private double swingHigh() throws TradingException {
		double sh = Input.High.get(1);
		for(int i = 2; i <= LookbackBars; i++) {
			double h = Input.High.get(i);
			if(h > sh) sh = h;
		}
		return sh;
	}

	private double swingLow() throws TradingException {
		double sl = Input.Low.get(1);
		for(int i = 2; i <= LookbackBars; i++) {
			double l = Input.Low.get(i);
			if(l < sl) sl = l;
		}
		return sl;
	}

	@Override
	protected void OnBarUpdate() throws TradingException {
		resetOutputs();
		barsSeen++;
		if(barsSeen < LookbackBars + 2) {
			return;
		}

		long barTime = Input.Time(0);
		int dk = dayKey(barTime);
		if(dk != dayKey) {
			dayKey = dk;
			tradesToday = 0;
		}
		if(!inSession(barTime) || tradesToday >= MaxTradesPerDay) {
			return;
		}

		double H = Input.High.get(0);
		double L = Input.Low.get(0);
		double C = Input.Close.get(0);
		double slip = SlBufferPips * pipSize();
		double sh = swingHigh();
		double sl = swingLow();

		// Sweep high -> short
		if(AllowShort && H > sh && C < sh) {
			double entry = C;
			double stop = H + slip;
			double risk = stop - entry;
			if(risk > 0) {
				double tp = entry - risk * TPRatio;
				if(tp > 0 && stop > entry && tp < entry) {
					ShortEntry.set(1);
					ShortStop.set(stop);
					ShortTP.set(tp);
					tradesToday++;
					return;
				}
			}
		}

		// Sweep low -> long
		if(AllowLong && L < sl && C > sl) {
			double entry = C;
			double stop = L - slip;
			double risk = entry - stop;
			if(risk > 0) {
				double tp = entry + risk * TPRatio;
				if(tp > entry && entry > stop) {
					LongEntry.set(1);
					LongStop.set(stop);
					LongTP.set(tp);
					tradesToday++;
				}
			}
		}
	}
}
