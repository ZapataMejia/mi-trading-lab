//+------------------------------------------------------------------+
//| HobbyCode_FondeoEMA.mq5                                          |
//| Cruce EMA 9/20 — metodologia evaluacion/fondeo (HobbyCode)       |
//|                                                                  |
//| PEGAR: MetaEditor MT5 -> Nuevo -> Expert Advisor -> pegar todo   |
//|        Compilar (F7) -> arrastrar a grafico EURUSD M5            |
//|                                                                  |
//| Para Copy Trading HobbyCode con parche: exportar desde SQX       |
//| (FondeoEMAcross.java). Este EA sirve para probar ya en demo.     |
//+------------------------------------------------------------------+
#property copyright "HobbyCode / evaluaciones"
#property version   "1.00"
#property strict

input int    InpFastEMA         = 9;
input int    InpSlowEMA         = 20;
input double InpRiskPct         = 1.0;    // % cuenta si toca SL (Instant WS ~1)
input double InpSLPricePct      = 1.0;    // distancia SL como % del precio
input double InpTPRatio         = 1.0;    // TP = SL * ratio (1 = 1:1)
input int    InpSessStartHHMM   = 800;    // 08:00
input int    InpSessEndHHMM     = 1000;   // 10:00
input int    InpMaxTradesDay    = 1;
input ulong  InpMagic           = 202606;
input int    InpSlippage        = 30;

int    g_handleFast;
int    g_handleSlow;
datetime g_lastBarTime = 0;
int    g_tradesToday   = 0;
int    g_dayKey        = -1;

//+------------------------------------------------------------------+
int OnInit()
{
   g_handleFast = iMA(_Symbol, PERIOD_CURRENT, InpFastEMA, 0, MODE_EMA, PRICE_CLOSE);
   g_handleSlow = iMA(_Symbol, PERIOD_CURRENT, InpSlowEMA, 0, MODE_EMA, PRICE_CLOSE);
   if(g_handleFast == INVALID_HANDLE || g_handleSlow == INVALID_HANDLE)
   {
      Print("Error creando EMAs: ", GetLastError());
      return INIT_FAILED;
   }
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(g_handleFast != INVALID_HANDLE) IndicatorRelease(g_handleFast);
   if(g_handleSlow != INVALID_HANDLE) IndicatorRelease(g_handleSlow);
}

//+------------------------------------------------------------------+
int DayKey(datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return dt.year * 10000 + dt.mon * 100 + dt.day;
}

//+------------------------------------------------------------------+
int TimeHHMM(datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return dt.hour * 100 + dt.min;
}

//+------------------------------------------------------------------+
bool InSession(datetime t)
{
   int hhmm = TimeHHMM(t);
   return (hhmm >= InpSessStartHHMM && hhmm <= InpSessEndHHMM);
}

//+------------------------------------------------------------------+
bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
double NormalizeLot(double lot)
{
   double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double stepLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(stepLot <= 0.0) stepLot = 0.01;

   lot = MathFloor(lot / stepLot) * stepLot;
   if(lot < minLot) lot = minLot;
   if(lot > maxLot) lot = maxLot;
   return lot;
}

//+------------------------------------------------------------------+
double CalcLot(double entry, double sl)
{
   double riskMoney = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPct / 100.0;
   double slDist    = MathAbs(entry - sl);
   if(slDist <= 0.0) return 0.0;

   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tickSize <= 0.0 || tickValue <= 0.0) return 0.0;

   double lossPerLot = (slDist / tickSize) * tickValue;
   if(lossPerLot <= 0.0) return 0.0;

   return NormalizeLot(riskMoney / lossPerLot);
}

//+------------------------------------------------------------------+
bool GetEMA(int handle, int shift, double &value)
{
   double buf[];
   ArraySetAsSeries(buf, true);
   if(CopyBuffer(handle, 0, shift, 1, buf) != 1) return false;
   value = buf[0];
   return true;
}

//+------------------------------------------------------------------+
bool SendOrder(ENUM_ORDER_TYPE type, double sl, double tp)
{
   MqlTradeRequest req;
   MqlTradeResult  res;
   ZeroMemory(req);
   ZeroMemory(res);

   double price = (type == ORDER_TYPE_BUY)
      ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
      : SymbolInfoDouble(_Symbol, SYMBOL_BID);

   double lot = CalcLot(price, sl);
   if(lot <= 0.0)
   {
      Print("Lote invalido");
      return false;
   }

   req.action       = TRADE_ACTION_DEAL;
   req.symbol       = _Symbol;
   req.volume       = lot;
   req.type         = type;
   req.price        = price;
   req.sl           = sl;
   req.tp           = tp;
   req.deviation    = InpSlippage;
   req.magic        = InpMagic;
   req.type_filling = ORDER_FILLING_FOK;

   if(!OrderSend(req, res))
   {
      req.type_filling = ORDER_FILLING_IOC;
      if(!OrderSend(req, res))
      {
         req.type_filling = ORDER_FILLING_RETURN;
         if(!OrderSend(req, res))
         {
            Print("OrderSend fallo: ", GetLastError());
            return false;
         }
      }
   }
   return true;
}

//+------------------------------------------------------------------+
void OnTick()
{
   datetime barTime = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(barTime == g_lastBarTime) return;
   g_lastBarTime = barTime;

   int dk = DayKey(barTime);
   if(dk != g_dayKey)
   {
      g_dayKey = dk;
      g_tradesToday = 0;
   }

   if(!InSession(barTime)) return;
   if(g_tradesToday >= InpMaxTradesDay) return;
   if(HasOpenPosition()) return;

   double emaFast0, emaFast1, emaSlow0, emaSlow1;
   if(!GetEMA(g_handleFast, 0, emaFast0)) return;
   if(!GetEMA(g_handleFast, 1, emaFast1)) return;
   if(!GetEMA(g_handleSlow, 0, emaSlow0)) return;
   if(!GetEMA(g_handleSlow, 1, emaSlow1)) return;

   bool crossUp = (emaFast1 <= emaSlow1 && emaFast0 > emaSlow0);
   bool crossDn = (emaFast1 >= emaSlow1 && emaFast0 < emaSlow0);
   if(!crossUp && !crossDn) return;

   double C = iClose(_Symbol, PERIOD_CURRENT, 0);
   double slDist = C * InpSLPricePct / 100.0;
   double tpDist = slDist * InpTPRatio;

   if(crossUp)
   {
      double sl = C - slDist;
      double tp = C + tpDist;
      if(SendOrder(ORDER_TYPE_BUY, sl, tp))
         g_tradesToday++;
   }
   else if(crossDn)
   {
      double sl = C + slDist;
      double tp = C - tpDist;
      if(SendOrder(ORDER_TYPE_SELL, sl, tp))
         g_tradesToday++;
   }
}
