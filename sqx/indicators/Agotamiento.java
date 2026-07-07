/*
 * Custom Indicator: Agotamiento (estrategia Cristian / TFT)
 * Portado 1:1 desde scripts/agotamiento_backtest.py (versión validada: PF 1.32 long-only).
 *
 * Entrada via orden STOP en la línea de agotamiento (igual que Python), NO a mercado.
 * El indicador "arma" el stop (LongEntry=1 + LongEntryPrice=línea) en cada vela mientras
 * el setup está vivo; AlgoWizard coloca un Buy/Sell Stop en ese precio. Cuando el precio
 * rompe la línea, el stop se ejecuta intrabar en la línea exacta -> ratio de pago real ~3.
 *
 * Salidas:
 *   LongEntry/ShortEntry   = 1 mientras el stop está armado (0 si no)
 *   LongEntryPrice/Short.. = precio donde colocar la orden stop (línea de agotamiento)
 *   LongStop/ShortStop     = precio de SL
 *   LongTP/ShortTP         = precio de TP
 */
package SQ.Blocks.Indicators.Custom;

import SQ.Internal.IndicatorBlock;

import com.strategyquant.lib.*;
import com.strategyquant.datalib.*;
import com.strategyquant.tradinglib.*;

@BuildingBlock(name="Agotamiento (TFT)", display="Agotamiento(@Chart@ sw#Swing# r#MinRetrace#)", returnType = ReturnTypes.Price)
@Help("Estrategia Agotamiento (Cristian/TFT). Entrada STOP en la linea de agotamiento. Outputs: LongEntry/ShortEntry (1/0), LongEntryPrice/ShortEntryPrice, LongStop/ShortStop, LongTP/ShortTP. Filtro de sesion ET integrado.")
@ParameterSet(set="Swing=2,MinRetrace=2")
@ParameterSet(set="Swing=2,MinRetrace=3")
public class Agotamiento extends IndicatorBlock {

	@Parameter
	public ChartData Input;

	@Parameter(defaultValue="2", minValue=1, maxValue=10, step=1)
	public int Swing;

	@Parameter(defaultValue="2", minValue=1, maxValue=10, step=1)
	public int MinRetrace;

	@Parameter(defaultValue="0", minValue=0, maxValue=100, step=0.1)
	public double SLBufferPoints;

	@Parameter(defaultValue="3", minValue=0.5, maxValue=10, step=0.1)
	public double TPRatio;

	// Ventana de sesion ET en formato HHMM (930 = 09:30, 1555 = 15:55).
	// Para desactivar el filtro: SessStart=0, SessEnd=2359.
	@Parameter(defaultValue="930", minValue=0, maxValue=2359, step=5)
	public int SessStart;

	@Parameter(defaultValue="1555", minValue=0, maxValue=2359, step=5)
	public int SessEnd;

	@Output(name="LongEntry")
	public DataSeries LongEntry;

	@Output(name="ShortEntry")
	public DataSeries ShortEntry;

	@Output(name="LongEntryPrice")
	public DataSeries LongEntryPrice;

	@Output(name="ShortEntryPrice")
	public DataSeries ShortEntryPrice;

	@Output(name="LongStop")
	public DataSeries LongStop;

	@Output(name="ShortStop")
	public DataSeries ShortStop;

	@Output(name="LongTP")
	public DataSeries LongTP;

	@Output(name="ShortTP")
	public DataSeries ShortTP;

	// ---- estado persistente entre velas ----
	private int barsSeen;
	private double lastSwingHigh;
	private double lastSwingLow;

	// máquina de estados LONG
	private boolean lImpulse;
	private double lModule, lExline, lRlow;
	private int lReds;

	// máquina de estados SHORT
	private boolean sImpulse;
	private double sModule, sExline, sRhigh;
	private int sGreens;

	//------------------------------------------------------------------------

	@Override
	protected void OnInit() throws TradingException {
		barsSeen = 0;
		lastSwingHigh = Double.NaN;
		lastSwingLow = Double.NaN;
		resetLong();
		resetShort();
	}

	private void resetLong() {
		lImpulse = false;
		lModule = Double.NaN;
		lExline = Double.NaN;
		lReds = 0;
		lRlow = Double.POSITIVE_INFINITY;
	}

	private void resetShort() {
		sImpulse = false;
		sModule = Double.NaN;
		sExline = Double.NaN;
		sGreens = 0;
		sRhigh = Double.NEGATIVE_INFINITY;
	}

	//------------------------------------------------------------------------

	@Override
	protected void OnBarUpdate() throws TradingException {
		// salidas por defecto (sin señal en esta vela)
		LongEntry.set(0);
		ShortEntry.set(0);
		LongEntryPrice.set(0);
		ShortEntryPrice.set(0);
		LongStop.set(0);
		ShortStop.set(0);
		LongTP.set(0);
		ShortTP.set(0);

		barsSeen++;
		int need = 2 * Swing + 1;
		if(barsSeen < need) {
			return;
		}

		// ---- swing pivote confirmado en la barra get(Swing) (sin mirar al futuro) ----
		double pvH = Input.High.get(Swing);
		double pvL = Input.Low.get(Swing);
		boolean isHigh = true, isLow = true;
		for(int i = 0; i <= 2 * Swing; i++) {
			if(i == Swing) continue;
			if(Input.High.get(i) >= pvH) isHigh = false;
			if(Input.Low.get(i)  <= pvL) isLow  = false;
		}
		if(isHigh) lastSwingHigh = pvH;
		if(isLow)  lastSwingLow  = pvL;

		double O = Input.Open.get(0);
		double H = Input.High.get(0);
		double L = Input.Low.get(0);
		double C = Input.Close.get(0);
		boolean bear = C < O;
		boolean bull = C > O;

		// filtro de sesion (los datos ya estan en hora de NY/ET)
		long barTime = Input.Time(0);
		int hhmm = SQTime.getHour(barTime) * 100 + SQTime.getMinute(barTime);
		boolean inSession = (hhmm >= SessStart && hhmm <= SessEnd);

		// =================== LONG ===================
		if(!lImpulse) {
			if(!Double.isNaN(lastSwingHigh) && C > lastSwingHigh && !Double.isNaN(lastSwingLow)) {
				lImpulse = true;
				lModule = lastSwingLow;
				lReds = 0;
				lRlow = Double.POSITIVE_INFINITY;
				lExline = Double.NaN;
			}
		} else {
			if(L < lModule) {
				resetLong();
			} else if(lReds >= MinRetrace && !Double.isNaN(lExline) && H > lExline) {
				// el buy-stop colocado en lExline se habria ejecutado intrabar -> setup consumido
				resetLong();
			} else if(bear) {
				lReds++;
				lExline = H;
				if(L < lRlow) lRlow = L;
			}
			// si seguimos armados, mantener el buy-stop en lExline para la proxima vela
			if(lImpulse && lReds >= MinRetrace && !Double.isNaN(lExline) && inSession) {
				double sl = lRlow - SLBufferPoints;
				double risk = lExline - sl;
				if(risk > 0) {
					LongEntryPrice.set(lExline);
					LongStop.set(sl);
					LongTP.set(lExline + TPRatio * risk);
					LongEntry.set(1);
				}
			}
		}

		// =================== SHORT (espejo) ===================
		if(!sImpulse) {
			if(!Double.isNaN(lastSwingLow) && C < lastSwingLow && !Double.isNaN(lastSwingHigh)) {
				sImpulse = true;
				sModule = lastSwingHigh;
				sGreens = 0;
				sRhigh = Double.NEGATIVE_INFINITY;
				sExline = Double.NaN;
			}
		} else {
			if(H > sModule) {
				resetShort();
			} else if(sGreens >= MinRetrace && !Double.isNaN(sExline) && L < sExline) {
				// el sell-stop colocado en sExline se habria ejecutado intrabar -> setup consumido
				resetShort();
			} else if(bull) {
				sGreens++;
				sExline = L;
				if(H > sRhigh) sRhigh = H;
			}
			if(sImpulse && sGreens >= MinRetrace && !Double.isNaN(sExline) && inSession) {
				double sl = sRhigh + SLBufferPoints;
				double risk = sl - sExline;
				if(risk > 0) {
					ShortEntryPrice.set(sExline);
					ShortStop.set(sl);
					ShortTP.set(sExline - TPRatio * risk);
					ShortEntry.set(1);
				}
			}
		}
	}
}
