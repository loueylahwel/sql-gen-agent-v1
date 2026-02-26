import pandas as pd
import streamlit as st

def _detect_chart_type(df: pd.DataFrame) -> str:
    cols = df.columns.tolist()
    dtypes = df.dtypes
    if len(cols) < 2:
        return "Table only"
    num_cols = [c for c in cols if pd.api.types.is_numeric_dtype(dtypes[c])]
    first_col = cols[0]
    if pd.api.types.is_datetime64_any_dtype(dtypes[first_col]):
        return "Line"
    if dtypes[first_col] == object:
        try:
            pd.to_datetime(df[first_col].iloc[:5])
            return "Line"
        except Exception:
            pass
    if len(cols) == 2 and len(num_cols) == 1:
        return "Bar"
    if len(num_cols) >= 2:
        return "Line"
    return "Bar"

def render_chart(df: pd.DataFrame, chart_type: str = "Auto") -> None:
    effective = chart_type if chart_type != "Auto" else _detect_chart_type(df)
    if effective == "Table only" or df.empty:
        st.dataframe(df, use_container_width=True)
        return
    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if not num_cols:
        st.dataframe(df, use_container_width=True)
        return
    non_num = [c for c in df.columns if c not in num_cols]
    plot_df = df.copy()
    if non_num:
        plot_df = plot_df.set_index(non_num[0])
    plot_df = plot_df[num_cols]
    if effective == "Bar":
        st.bar_chart(plot_df, use_container_width=True)
    elif effective == "Line":
        st.line_chart(plot_df, use_container_width=True)
    elif effective == "Area":
        st.area_chart(plot_df, use_container_width=True)
    elif effective == "Scatter" and len(num_cols) >= 2:
        st.scatter_chart(plot_df, x=num_cols[0], y=num_cols[1], use_container_width=True)
    else:
        st.bar_chart(plot_df, use_container_width=True)