import streamlit as st
import requests, redis
import config, json
from iex import IEXStock
from helpers import format_number
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

def get_dcf(balancesheet, cashflow, income, stats):
    df_balancesheet = pd.json_normalize(balancesheet, record_path =['balancesheet'])
    df_cashflow = pd.json_normalize(cashflow, record_path =['cashflow'])                           
    df_income = pd.json_normalize(income, record_path =['income'])

    df = pd.concat([df_income[['symbol','fiscalYear','totalRevenue', 'netIncome']], df_cashflow[['cashFlow','capitalExpenditures']],df_balancesheet[['currentLongTermDebt', 'longTermDebt']]],axis=1)
    df['fcfEquity'] = df.cashFlow + df.capitalExpenditures
    df['fcfByTotalRevenue'] = df.fcfEquity/df.totalRevenue
    df['fcfByNetIncome'] = df.fcfEquity/df.netIncome
    df = df.iloc[::-1].reset_index().drop('index',axis=1)
    
    future_years = np.r_[df.fiscalYear.max()+1:2026]
    for i in future_years:
        df = df.append(pd.Series({'fiscalYear':i}), ignore_index=True)
    
    df['symbol'] = df.symbol[0]  
    df['revenueGrowthRate'] = 0
    df['netIncomeMargin'] = 0  

    for i in range(1, len(df)):
        df.loc[i,'revenueGrowthRate'] = (df.loc[i,'totalRevenue'] - df.loc[i-1,'totalRevenue'])/df.loc[i-1,'totalRevenue']
    
    average_revenue_growth_rate = df.iloc[1:4,:].revenueGrowthRate.sum()/len(df.iloc[1:4,:])
    df.netIncomeMargin = df.netIncome/df.totalRevenue
    average_net_income_margin = df.iloc[0:4,:].netIncomeMargin.sum()/len(df.iloc[0:4,:])
    average_fcfByNetIncome = df.iloc[0:4,:].fcfByNetIncome.sum()/len(df.iloc[0:4,:])    
    average_fcfByTotalRevenue = df.iloc[0:4,:].fcfByTotalRevenue.sum()/len(df.iloc[0:4,:])
    
    for i in range(4, len(df)):
        df.loc[i,'totalRevenue'] = df.loc[i-1,'totalRevenue']*(1+average_revenue_growth_rate)
        df.loc[i,'netIncome'] = df.loc[i-1,'netIncome']*(1+average_net_income_margin)

    df.iloc[4:df.shape[0]]['fcfEquity'] = df.iloc[4:df.shape[0]]['netIncome']*(average_fcfByNetIncome)
    df = df.append(pd.Series({'fiscalYear':9999}), ignore_index=True)
    
    df['discountFactor'] = 0
    
    ltGrowthRate = .02
    wacc = .1
    df.loc[df.index>3, 'discountFactor'] = (1+wacc)**(df.loc[df.index>3].index-3)

    df.loc[len(df)-1,'fcfEquity'] = (df.loc[len(df)-2,'fcfEquity']*(1+ltGrowthRate))/(wacc-ltGrowthRate)
    df.loc[len(df)-1,'discountFactor'] = df.loc[len(df)-2,'discountFactor']

    df['pvFutureCashflow'] = 0
    df.loc[df.index>3, 'pvFutureCashflow'] = df.loc[df.index>3,'fcfEquity']/df.loc[df.index>3,'discountFactor']
    
    return df.pvFutureCashflow.sum()/stats['sharesOutstanding']
    
    

symbol = st.sidebar.text_input("Symbol", value='AAPL')

stock = IEXStock(config.IEX_TOKEN, symbol, environment='production')

client = redis.Redis(host="localhost", port=6379)

screen = st.sidebar.selectbox("View", ('Overview', 'Fundamentals', 'DCF'), index=2)

st.title(screen)

if screen == 'Overview':
    logo_cache_key = f"{symbol}_logo"
    cached_logo = client.get(logo_cache_key)
    
    if cached_logo is not None:
        print("found logo in cache")
        logo = json.loads(cached_logo)
    else:
        print("getting logo from api, and then storing it in cache")
        logo = stock.get_logo()
        client.set(logo_cache_key, json.dumps(logo))
        client.expire(logo_cache_key, timedelta(hours=24))
    
    # company_cache_key = f"{symbol}_company"
    # cached_company_info = client.get(company_cache_key)
    
    col1, col2 = st.beta_columns([1, 4])
    with col1:
        st.image(logo['url'])
        
if screen == 'DCF':
    #get stats
    stats_cache_key = f"{symbol}_stats"
    stats = client.get(stats_cache_key)
   
    if stats is None:
        stats = stock.get_stats()
        client.set(stats_cache_key, json.dumps(stats))
    else:
        stats = json.loads(stats)
        print('getting stats from cache')
    
    # get balance sheet    
    balancesheet_cache_key = f"{symbol}_balancesheet"
    balancesheet = client.get(balancesheet_cache_key)
   
    if balancesheet is None:
        balancesheet = stock.get_balancesheet(last=4)
        client.set(balancesheet_cache_key, json.dumps(balancesheet))
    else:
        balancesheet = json.loads(balancesheet)
    
    #get income statement    
    income_cache_key = f"{symbol}_income"
    income = client.get(income_cache_key)
   
    if income is None:
        income = stock.get_income(last=4)
        client.set(income_cache_key, json.dumps(income))
    else:
        income = json.loads(income)
        
    
    #get cashflow statement    
    cashflow_cache_key = f"{symbol}_cashflow"
    cashflow = client.get(cashflow_cache_key)
   
    if cashflow is None:
        cashflow = stock.get_cashflow(last=4)
        client.set(cashflow_cache_key, json.dumps(cashflow))
    else:
        cashflow = json.loads(cashflow)
    
    fv_equity = get_dcf(balancesheet, cashflow, income,stats)
    st.subheader('Fair value of Equity using DCF1')
    st.write(fv_equity)
    
    
      
   