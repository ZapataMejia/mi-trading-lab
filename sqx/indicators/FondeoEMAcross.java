/*
 * Custom Indicator: Fondeo EMA Cross (metodologia HobbyCode / evaluaciones)
 *
 * PEGAR EN SQX: Code Editor -> New Snippet -> Indicator -> pegar -> Compile.
 *
 * Cruce EMA 9/20 en M5. Estrategia "de usar y tirar" (NO busca edge historico).
 * SQX no permite importar estrategia completa desde fuera; tras compilar este
 * indicador, en AlgoWizard solo hay que armar 2 reglas (ver abajo) y exportar.
 *
 * AlgoWizard (2 reglas, ~2 min):
 *   Long:  FondeoEMAcross.LongEntry  > 0  -> Enter at Market, SL=LongStop, TP=LongTP
 *   Short: FondeoEMAcross.ShortEntry > 0  -> Enter at Market, SL=ShortStop, TP=ShortTP
 *
 * Export a MT5 solo cuando pase backtest y vayais a cuenta real (parcheador HobbyCode).
 */
package SQ.Blocks.Indicators.Custom;

import SQ.Internal.IndicatorBlock;

import com.strategyquant.lib.*;
import com.strategyquant.datalib.*;
import com.strategyquant.tradinglib.*;

@BuildingBlock(name="Fondeo EMA Cross", display="FondeoEMA(@Chart@ f#FastPeriod# s#SlowPeriod#)", returnType = ReturnTypes.Price)
@Help("Cruce EMA para evaluaciones de fondeo. Outputs: LongEntry/ShortEntry (pulso 1/0), LongStop/ShortStop, LongTP/ShortTP. Filtro sesion + max trades/dia.")
@ParameterSet(set="FastPeriod=9,SlowPeriod=20,RiskPct=1.0,TPRatio=1.0,MaxTradesPerDay=1")
@ParameterSet(set="FastPeriod=9,SlowPeriod=20,RiskPct=2.1,TPRatio=1.0,MaxTradesPerDay=2")
@ParameterSet(set="FastPeriod=9,SlowPeriod=20,RiskPct=4.0,TPRatio=1.0,MaxTradesPerDay=2")
public class FondeoEMAcross extends IndicatorBlock {

	@Parameter
	public ChartData Input;

	@Parameter(defaultValue="9", minValue=2, maxValue=50, step=1)
	public int FastPeriod;

	@Parameter(defaultValue="20", minValue=3, maxValue=200, step=1)
	public int SlowPeriod;

	/** Distancia SL como % del precio de entrada (Instant WS ~1; eval WS ~2.1). */
	@Parameter(defaultValue="2.1", minValue=0.5, maxValue=10, step=0.1)
	public double RiskPct;

	/** TP = entrada +/- RiskPct * TPRatio (1.0 = riesgo 1:1). */
	@Parameter(defaultValue="1.0", minValue=0.5, maxValue=5, step=0.1)
	public double TPRatio;

	/** Ventana sesion HHMM (800=08:00). 0 + 2359 = sin filtro. */
	@Parameter(defaultValue="800", minValue=0, maxValue=2359, step=5)
	public int SessStart;

	@Parameter(defaultValue="1000", minValue=0, maxValue=2359, step=5)
	public int SessEnd;

	@Parameter(defaultValue="2", minValue=1, maxValue=10, step=1)
	public int MaxTradesPerDay;

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

	private double emaFast;
	private double emaSlow;
	private double prevEmaFast;
	private double prevEmaSlow;
	private int barsSeen;

	private int dayKey;
	private int tradesToday;

	@Override
	protected void OnInit() throws TradingException {
		emaFast = Double.NaN;
		emaSlow = Double.NaN;
		prevEmaFast = Double.NaN;
		prevEmaSlow = Double.NaN;
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

	private void resetOutputs() throws TradingException {
		LongEntry.set(0);
		ShortEntry.set(0);
		LongStop.set(0);
		ShortStop.set(0);
		LongTP.set(0);
		ShortTP.set(0);
	}

	@Override
	protected void OnBarUpdate() throws TradingException {
		resetOutputs();

		barsSeen++;
		int need = Math.max(FastPeriod, SlowPeriod) + 2;
		if(barsSeen < need) {
			return;
		}

		double C = Input.Close.get(0);
		long barTime = Input.Time(0);
		int dk = dayKey(barTime);
		if(dk != dayKey) {
			dayKey = dk;
			tradesToday = 0;
		}

		double kF = 2.0 / (FastPeriod + 1.0);
		double kS = 2.0 / (SlowPeriod + 1.0);

		prevEmaFast = emaFast;
		prevEmaSlow = emaSlow;

		if(Double.isNaN(emaFast)) {
			emaFast = C;
			emaSlow = C;
			return;
		}

		emaFast = C * kF + emaFast * (1.0 - kF);
		emaSlow = C * kS + emaSlow * (1.0 - kS);

		if(Double.isNaN(prevEmaFast)) {
			return;
		}

		if(!inSession(barTime)) {
			return;
		}
		if(tradesToday >= MaxTradesPerDay) {
			return;
		}

		boolean crossUp = prevEmaFast <= prevEmaSlow && emaFast > emaSlow;
		boolean crossDn = prevEmaFast >= prevEmaSlow && emaFast < emaSlow;

		double riskFrac = RiskPct / 100.0;
		double tpFrac = riskFrac * TPRatio;

		if(crossUp) {
			double sl = C * (1.0 - riskFrac);
			double tp = C * (1.0 + tpFrac);
			if(sl > 0 && tp > C) {
				LongEntry.set(1);
				LongStop.set(sl);
				LongTP.set(tp);
				tradesToday++;
			}
		} else if(crossDn) {
			double sl = C * (1.0 + riskFrac);
			double tp = C * (1.0 - tpFrac);
			if(tp > 0 && sl > C) {
				ShortEntry.set(1);
				ShortStop.set(sl);
				ShortTP.set(tp);
				tradesToday++;
			}
		}
	}
}
