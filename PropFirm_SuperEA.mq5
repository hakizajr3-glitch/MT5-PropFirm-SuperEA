//+------------------------------------------------------------------+
//|                                            PropFirm_SuperEA.mq5   |
//|                              Copyright 2026, MT5-PropFirm-SuperEA |
//|                                       https://www.mql5.com        |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, MT5-PropFirm-SuperEA"
#property link      "https://github.com/hakizajr3-glitch/MT5-PropFirm-SuperEA"
#property version   "3.00"
#property description "Trend-following EA (EMA + ATR) with prop-firm risk controls:"
#property description "risk-% sizing, daily-loss limit, max drawdown, session filter,"
#property description "spread filter, break-even and trailing stop."

#include <Trade/Trade.mqh>
#include <Trade/SymbolInfo.mqh>

//============================ INPUTS ================================//
input group "=== Strategy ==="
input int      InpFastEMA          = 20;      // Fast EMA period
input int      InpSlowEMA          = 50;      // Slow EMA period
input int      InpATRPeriod        = 14;      // ATR period (volatility)
input double   InpSL_ATR           = 1.5;     // Stop loss = ATR x this
input double   InpTP_ATR           = 2.5;     // Take profit = ATR x this
input bool     InpUseRSIFilter     = true;    // Use RSI trend filter
input int      InpRSIPeriod        = 14;      // RSI period
input double   InpRSIBuyMin        = 50.0;    // Buy only if RSI >= this
input double   InpRSISellMax       = 50.0;    // Sell only if RSI <= this

input group "=== Money / Risk Management ==="
input bool     InpUseRiskPercent   = true;    // Size lots by risk % (else fixed lot)
input double   InpRiskPercent      = 1.0;     // Risk per trade (% of balance)
input double   InpFixedLot         = 0.10;    // Fixed lot (if risk % disabled)
input int      InpMaxOpenPositions = 1;       // Max simultaneous positions (this EA)
input int      InpMaxSpreadPoints  = 50;      // Max allowed spread (points, 0=off)

input group "=== Prop-Firm Guardrails ==="
input double   InpMaxDailyLossPct  = 5.0;     // Max daily loss (% of day-start equity)
input double   InpMaxTotalDDPct    = 10.0;    // Max total drawdown (% from peak equity)
input bool     InpCloseOnDailyStop = true;    // Close all positions when daily limit hit
input bool     InpCloseOnTotalStop = true;    // Close all positions when total DD hit

input group "=== Session Filter ==="
input bool     InpUseSession       = true;    // Restrict trading to a session window
input int      InpStartHour        = 7;       // Session start hour (server time)
input int      InpEndHour          = 20;      // Session end hour (server time)
input bool     InpTradeMonday      = true;    // Trade Monday
input bool     InpTradeFriday      = true;    // Trade Friday

input group "=== Exit Management ==="
input bool     InpUseBreakEven     = true;    // Move SL to break-even
input double   InpBE_TriggerPoints = 150;     // Profit (points) to trigger break-even
input double   InpBE_LockPoints    = 20;      // Points locked above entry at break-even
input bool     InpUseTrailing      = true;    // Use trailing stop
input double   InpTrailStartPoints = 200;     // Profit (points) before trailing starts
input double   InpTrailStepPoints  = 100;     // Trailing distance (points)

input group "=== General ==="
input long     InpMagicNumber      = 260621;  // Magic number (unique per EA)
input string   InpTradeComment     = "PropFirm_SuperEA"; // Order comment

//============================ GLOBALS ==============================//
CTrade         trade;
CSymbolInfo    sym;

int      hFastEMA = INVALID_HANDLE;
int      hSlowEMA = INVALID_HANDLE;
int      hATR     = INVALID_HANDLE;
int      hRSI     = INVALID_HANDLE;

datetime g_lastBarTime   = 0;
int      g_currentDay    = -1;
double   g_dayStartEquity= 0.0;
double   g_peakEquity    = 0.0;
bool     g_dailyLocked   = false;   // daily loss limit reached today
bool     g_totalLocked   = false;   // total drawdown limit reached

string   g_gvDay   = "";            // global-var names (persist across restarts)
string   g_gvDayEq = "";
string   g_gvPeak  = "";

//+------------------------------------------------------------------+
//| Helper: points -> price distance                                 |
//+------------------------------------------------------------------+
double PointsToPrice(double points)
{
   return points * _Point;
}

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   if(InpFastEMA <= 0 || InpSlowEMA <= 0 || InpFastEMA >= InpSlowEMA)
   {
      Print("Init error: require 0 < FastEMA < SlowEMA");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(!sym.Name(_Symbol))
   {
      Print("Init error: cannot select symbol ", _Symbol);
      return INIT_FAILED;
   }

   hFastEMA = iMA(_Symbol, _Period, InpFastEMA, 0, MODE_EMA, PRICE_CLOSE);
   hSlowEMA = iMA(_Symbol, _Period, InpSlowEMA, 0, MODE_EMA, PRICE_CLOSE);
   hATR     = iATR(_Symbol, _Period, InpATRPeriod);
   hRSI     = iRSI(_Symbol, _Period, InpRSIPeriod, PRICE_CLOSE);

   if(hFastEMA == INVALID_HANDLE || hSlowEMA == INVALID_HANDLE ||
      hATR == INVALID_HANDLE || hRSI == INVALID_HANDLE)
   {
      Print("Init error: failed to create indicator handles");
      return INIT_FAILED;
   }

   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetMarginMode();
   trade.SetTypeFillingBySymbol(_Symbol);
   trade.SetDeviationInPoints(20);

   // Persisted baselines (survive terminal restarts within the same account)
   g_gvDay   = "PFSEA_" + _Symbol + "_" + (string)InpMagicNumber + "_DAY";
   g_gvDayEq = "PFSEA_" + _Symbol + "_" + (string)InpMagicNumber + "_DAYEQ";
   g_gvPeak  = "PFSEA_" + _Symbol + "_" + (string)InpMagicNumber + "_PEAK";

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   g_peakEquity  = GlobalVariableCheck(g_gvPeak) ? GlobalVariableGet(g_gvPeak) : equity;
   if(g_peakEquity < equity) g_peakEquity = equity;

   ResetDailyBaselineIfNeeded(true);

   Print("PropFirm_SuperEA v3.00 initialized on ", _Symbol, " ", EnumToString(_Period));
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(hFastEMA != INVALID_HANDLE) IndicatorRelease(hFastEMA);
   if(hSlowEMA != INVALID_HANDLE) IndicatorRelease(hSlowEMA);
   if(hATR     != INVALID_HANDLE) IndicatorRelease(hATR);
   if(hRSI     != INVALID_HANDLE) IndicatorRelease(hRSI);
   Print("PropFirm_SuperEA deinitialized (reason ", reason, ")");
}

//+------------------------------------------------------------------+
//| Expert tick                                                      |
//+------------------------------------------------------------------+
void OnTick()
{
   ResetDailyBaselineIfNeeded(false);
   UpdatePeakEquity();

   // When a risk limit is breached, stop opening new trades for the day.
   if(CheckRiskLimits())
      return;

   // Manage existing positions on every tick (break-even / trailing).
   ManageOpenPositions();

   // New entries only once per closed bar.
   if(!IsNewBar())
      return;

   if(InpUseSession && !InSession())
      return;

   if(CountOwnPositions() >= InpMaxOpenPositions)
      return;

   if(!SpreadOK())
      return;

   int signal = GetSignal(); // +1 buy, -1 sell, 0 none
   if(signal == 0)
      return;

   OpenTrade(signal);
}

//+------------------------------------------------------------------+
//| New bar detection                                                |
//+------------------------------------------------------------------+
bool IsNewBar()
{
   datetime t = (datetime)SeriesInfoInteger(_Symbol, _Period, SERIES_LASTBAR_DATE);
   if(t != g_lastBarTime)
   {
      g_lastBarTime = t;
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Session / day filter                                             |
//+------------------------------------------------------------------+
bool InSession()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);

   if(dt.day_of_week == 0 || dt.day_of_week == 6) return false; // Sun/Sat
   if(!InpTradeMonday && dt.day_of_week == 1)     return false;
   if(!InpTradeFriday && dt.day_of_week == 5)     return false;

   if(InpStartHour <= InpEndHour)
      return (dt.hour >= InpStartHour && dt.hour < InpEndHour);
   // window wrapping midnight
   return (dt.hour >= InpStartHour || dt.hour < InpEndHour);
}

//+------------------------------------------------------------------+
//| Spread filter                                                    |
//+------------------------------------------------------------------+
bool SpreadOK()
{
   if(InpMaxSpreadPoints <= 0) return true;
   long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if(spread > InpMaxSpreadPoints)
   {
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| Strategy signal: EMA cross + optional RSI filter                 |
//| Uses closed bars (shift 1 vs 2) to avoid repainting              |
//+------------------------------------------------------------------+
int GetSignal()
{
   double fast[3], slow[3], rsi[2];
   ArraySetAsSeries(fast, true);
   ArraySetAsSeries(slow, true);
   ArraySetAsSeries(rsi,  true);
   if(CopyBuffer(hFastEMA, 0, 0, 3, fast) < 3) return 0;
   if(CopyBuffer(hSlowEMA, 0, 0, 3, slow) < 3) return 0;

   // index 0=current(forming), 1=last closed, 2=prev closed
   bool crossUp   = (fast[2] <= slow[2] && fast[1] > slow[1]);
   bool crossDown = (fast[2] >= slow[2] && fast[1] < slow[1]);

   if(InpUseRSIFilter)
   {
      if(CopyBuffer(hRSI, 0, 0, 2, rsi) < 2) return 0;
      if(crossUp   && rsi[1] < InpRSIBuyMin)  crossUp   = false;
      if(crossDown && rsi[1] > InpRSISellMax) crossDown = false;
   }

   if(crossUp)   return  1;
   if(crossDown) return -1;
   return 0;
}

//+------------------------------------------------------------------+
//| Open a trade with ATR-based SL/TP and risk-based sizing          |
//+------------------------------------------------------------------+
void OpenTrade(int signal)
{
   double atr[1];
   if(CopyBuffer(hATR, 0, 1, 1, atr) < 1) return;
   double atrVal = atr[0];
   if(atrVal <= 0) return;

   sym.RefreshRates();
   double ask = sym.Ask();
   double bid = sym.Bid();
   int    digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);

   double slDist = atrVal * InpSL_ATR;
   double tpDist = atrVal * InpTP_ATR;

   double price, sl, tp;
   if(signal > 0)
   {
      price = ask;
      sl    = NormalizeDouble(price - slDist, digits);
      tp    = NormalizeDouble(price + tpDist, digits);
   }
   else
   {
      price = bid;
      sl    = NormalizeDouble(price + slDist, digits);
      tp    = NormalizeDouble(price - tpDist, digits);
   }

   double lots = CalcLotSize(slDist);
   if(lots <= 0)
   {
      Print("Lot size computed as 0 - skipping entry");
      return;
   }

   bool ok;
   if(signal > 0)
      ok = trade.Buy(lots, _Symbol, price, sl, tp, InpTradeComment);
   else
      ok = trade.Sell(lots, _Symbol, price, sl, tp, InpTradeComment);

   if(!ok)
      Print("Order failed: retcode=", trade.ResultRetcode(),
            " (", trade.ResultRetcodeDescription(), ")");
   else
      Print(signal > 0 ? "BUY" : "SELL", " opened ", lots, " lots @ ", price,
            " SL=", sl, " TP=", tp);
}

//+------------------------------------------------------------------+
//| Risk-based position sizing                                        |
//+------------------------------------------------------------------+
double CalcLotSize(double slDistancePrice)
{
   double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   if(!InpUseRiskPercent)
      return NormalizeVolume(InpFixedLot, minLot, maxLot, lotStep);

   double balance   = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskMoney = balance * InpRiskPercent / 100.0;

   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickSize <= 0 || tickValue <= 0 || slDistancePrice <= 0)
      return NormalizeVolume(InpFixedLot, minLot, maxLot, lotStep);

   double lossPerLot = (slDistancePrice / tickSize) * tickValue;
   if(lossPerLot <= 0)
      return NormalizeVolume(InpFixedLot, minLot, maxLot, lotStep);

   double lots = riskMoney / lossPerLot;
   return NormalizeVolume(lots, minLot, maxLot, lotStep);
}

double NormalizeVolume(double lots, double minLot, double maxLot, double lotStep)
{
   if(lotStep <= 0) lotStep = 0.01;
   lots = MathFloor(lots / lotStep) * lotStep;
   if(lots < minLot) lots = minLot;
   if(lots > maxLot) lots = maxLot;
   return NormalizeDouble(lots, 2);
}

//+------------------------------------------------------------------+
//| Break-even + trailing stop on own positions                      |
//+------------------------------------------------------------------+
void ManageOpenPositions()
{
   if(!InpUseBreakEven && !InpUseTrailing) return;

   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   sym.RefreshRates();

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;

      long   type   = PositionGetInteger(POSITION_TYPE);
      double open   = PositionGetDouble(POSITION_PRICE_OPEN);
      double curSL  = PositionGetDouble(POSITION_SL);
      double curTP  = PositionGetDouble(POSITION_TP);
      double bid    = sym.Bid();
      double ask    = sym.Ask();

      double newSL = curSL;

      if(type == POSITION_TYPE_BUY)
      {
         double profitPts = (bid - open) / _Point;
         if(InpUseBreakEven && profitPts >= InpBE_TriggerPoints)
         {
            double be = NormalizeDouble(open + PointsToPrice(InpBE_LockPoints), digits);
            if(be > newSL) newSL = be;
         }
         if(InpUseTrailing && profitPts >= InpTrailStartPoints)
         {
            double trail = NormalizeDouble(bid - PointsToPrice(InpTrailStepPoints), digits);
            if(trail > newSL) newSL = trail;
         }
         if(newSL > curSL && newSL < bid)
            trade.PositionModify(ticket, newSL, curTP);
      }
      else if(type == POSITION_TYPE_SELL)
      {
         double profitPts = (open - ask) / _Point;
         if(InpUseBreakEven && profitPts >= InpBE_TriggerPoints)
         {
            double be = NormalizeDouble(open - PointsToPrice(InpBE_LockPoints), digits);
            if(curSL == 0 || be < newSL) newSL = be;
         }
         if(InpUseTrailing && profitPts >= InpTrailStartPoints)
         {
            double trail = NormalizeDouble(ask + PointsToPrice(InpTrailStepPoints), digits);
            if(curSL == 0 || trail < newSL) newSL = trail;
         }
         if((curSL == 0 || newSL < curSL) && newSL > ask)
            trade.PositionModify(ticket, newSL, curTP);
      }
   }
}

//+------------------------------------------------------------------+
//| Count this EA's open positions on this symbol                    |
//+------------------------------------------------------------------+
int CountOwnPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      count++;
   }
   return count;
}

//+------------------------------------------------------------------+
//| Close all positions opened by this EA                            |
//+------------------------------------------------------------------+
void CloseAllOwnPositions(string reason)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(!trade.PositionClose(ticket))
         Print("Failed to close #", ticket, " (", reason, "): ",
               trade.ResultRetcodeDescription());
   }
}

//+------------------------------------------------------------------+
//| Daily baseline handling (resets each new day)                    |
//+------------------------------------------------------------------+
void ResetDailyBaselineIfNeeded(bool force)
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   int today = dt.year * 10000 + dt.mon * 100 + dt.day;

   int storedDay = GlobalVariableCheck(g_gvDay) ? (int)GlobalVariableGet(g_gvDay) : -1;

   if(force && storedDay == today)
   {
      g_currentDay     = today;
      g_dayStartEquity = GlobalVariableCheck(g_gvDayEq)
                         ? GlobalVariableGet(g_gvDayEq)
                         : AccountInfoDouble(ACCOUNT_EQUITY);
      g_dailyLocked    = false;
      return;
   }

   if(today != g_currentDay)
   {
      g_currentDay     = today;
      g_dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      g_dailyLocked    = false;
      GlobalVariableSet(g_gvDay,   today);
      GlobalVariableSet(g_gvDayEq, g_dayStartEquity);
      Print("New trading day. Day-start equity = ", g_dayStartEquity);
   }
}

//+------------------------------------------------------------------+
//| Track peak equity for total drawdown                             |
//+------------------------------------------------------------------+
void UpdatePeakEquity()
{
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity > g_peakEquity)
   {
      g_peakEquity = equity;
      GlobalVariableSet(g_gvPeak, g_peakEquity);
   }
}

//+------------------------------------------------------------------+
//| Prop-firm risk checks. Returns true if trading is locked.        |
//+------------------------------------------------------------------+
bool CheckRiskLimits()
{
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);

   // Daily loss limit
   if(InpMaxDailyLossPct > 0 && g_dayStartEquity > 0)
   {
      double dailyLossPct = (g_dayStartEquity - equity) / g_dayStartEquity * 100.0;
      if(dailyLossPct >= InpMaxDailyLossPct)
      {
         if(!g_dailyLocked)
         {
            Print("DAILY LOSS LIMIT hit: ", DoubleToString(dailyLossPct, 2),
                  "% >= ", InpMaxDailyLossPct, "%. Trading halted for today.");
            if(InpCloseOnDailyStop) CloseAllOwnPositions("daily loss limit");
         }
         g_dailyLocked = true;
      }
   }

   // Total drawdown limit
   if(InpMaxTotalDDPct > 0 && g_peakEquity > 0)
   {
      double totalDDPct = (g_peakEquity - equity) / g_peakEquity * 100.0;
      if(totalDDPct >= InpMaxTotalDDPct)
      {
         if(!g_totalLocked)
         {
            Print("TOTAL DRAWDOWN LIMIT hit: ", DoubleToString(totalDDPct, 2),
                  "% >= ", InpMaxTotalDDPct, "%. Trading halted.");
            if(InpCloseOnTotalStop) CloseAllOwnPositions("total drawdown limit");
         }
         g_totalLocked = true;
      }
   }

   return (g_dailyLocked || g_totalLocked);
}
//+------------------------------------------------------------------+
