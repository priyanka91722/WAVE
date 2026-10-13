import os
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import (accuracy_score, balanced_accuracy_score,
                             classification_report, confusion_matrix, f1_score,
                             mean_absolute_error, mean_squared_error,
                             precision_score, r2_score, recall_score, roc_auc_score)
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

st.set_page_config(page_title="Spoilage Predictor", layout="wide")
from style import inject_css
inject_css()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = PROJECT_ROOT / "data" / "cleaned" / "waste_cleaned.csv"

TARGET = "IsSpoiled"
LEAKY = ["IsSpoiled", "Waste_Status", "SpoilageChance", "Waste_Qty",
         "SuggestedAction", "StoreID", "ArrivalDate", "ExpiryDate"]

if not os.path.exists(CSV_PATH):
    st.error(f"CSV not found: {CSV_PATH}. Fix CSV_PATH at the top of this file.")
    st.stop()


@st.cache_resource
def train_model(path):
    df = pd.read_csv(path)
    y = df[TARGET].astype(str).str.lower().isin(["true", "1", "yes"]).astype(int)

    feats = []
    for c in df.columns:
        low = c.lower()
        if c in LEAKY or "date" in low or low.endswith("id"):
            continue
        if df[c].dtype == object and df[c].nunique() > 30:
            continue
        feats.append(c)

    X = df[feats].copy()
    cat_options, num_info = {}, {}
    for c in feats:
        if X[c].dtype == object or X[c].dtype == bool:
            X[c] = X[c].astype("string")
            cat_options[c] = sorted(X[c].dropna().astype(str).unique().tolist())
        else:
            is_int = bool((X[c].dropna() % 1 == 0).all())
            num_info[c] = (X[c].min(), X[c].max(), X[c].median(), is_int)

    categorical = [c for c in feats if c in cat_options]
    numeric = [c for c in feats if c in num_info]

    def make_model():
        preprocess = ColumnTransformer([
            ("categorical", Pipeline([
                ("impute", SimpleImputer(strategy="most_frequent")),
                ("encode", OneHotEncoder(handle_unknown="ignore")),
            ]), categorical),
            ("numeric", SimpleImputer(strategy="median"), numeric),
        ])
        return Pipeline([
            ("preprocess", preprocess),
            ("classifier", RandomForestClassifier(n_estimators=200, random_state=42)),
        ])

    def make_regression_model():
        preprocess = ColumnTransformer([
            ("categorical", Pipeline([
                ("impute", SimpleImputer(strategy="most_frequent")),
                ("encode", OneHotEncoder(handle_unknown="ignore")),
            ]), categorical),
            ("numeric", SimpleImputer(strategy="median"), numeric),
        ])
        return Pipeline([
            ("preprocess", preprocess),
            ("regressor", RandomForestRegressor(n_estimators=200, random_state=42)),
        ])

    # Hold out all rows for each product name together, preventing repeated
    # products from leaking across train and test folds.
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
    oof_pred = np.zeros(len(df), dtype=int)
    oof_prob = np.zeros(len(df), dtype=float)
    for train_idx, test_idx in cv.split(X, y, groups=df["ItemName"]):
        fold_model = make_model()
        fold_model.fit(X.iloc[train_idx], y.iloc[train_idx])
        oof_pred[test_idx] = fold_model.predict(X.iloc[test_idx])
        spoiled_idx = list(fold_model.classes_).index(1)
        oof_prob[test_idx] = fold_model.predict_proba(X.iloc[test_idx])[:, spoiled_idx]

    # Waste_Qty is the numeric regression target (wasted stock units). Group
    # folds by item name so records for a product cannot appear in both sets.
    regression_y = pd.to_numeric(df["Waste_Qty"], errors="raise").astype(float)
    regression_oof_pred = np.zeros(len(df), dtype=float)
    regression_cv = GroupKFold(n_splits=5)
    for train_idx, test_idx in regression_cv.split(X, regression_y, groups=df["ItemName"]):
        fold_model = make_regression_model()
        fold_model.fit(X.iloc[train_idx], regression_y.iloc[train_idx])
        regression_oof_pred[test_idx] = fold_model.predict(X.iloc[test_idx])

    regression_metrics = {
        "mae": mean_absolute_error(regression_y, regression_oof_pred),
        "rmse": mean_squared_error(regression_y, regression_oof_pred) ** 0.5,
        "r2": r2_score(regression_y, regression_oof_pred),
    }
    regression_predictions = df[["ItemName", "StoreLocation"]].copy()
    regression_predictions["Actual wasted quantity (units)"] = regression_y
    regression_predictions["Predicted wasted quantity (units)"] = regression_oof_pred
    regression_predictions["Absolute error (units)"] = (
        regression_y - regression_oof_pred
    ).abs()

    cm = confusion_matrix(y, oof_pred, labels=[0, 1])
    report = classification_report(
        y, oof_pred, labels=[0, 1], target_names=["Not spoiled", "Spoiled"],
        output_dict=True, zero_division=0,
    )
    metrics = {
        "accuracy": accuracy_score(y, oof_pred),
        "balanced_accuracy": balanced_accuracy_score(y, oof_pred),
        "precision": precision_score(y, oof_pred, zero_division=0),
        "recall": recall_score(y, oof_pred, zero_division=0),
        "f1": f1_score(y, oof_pred, zero_division=0),
        "roc_auc": roc_auc_score(y, oof_prob),
    }
    test_predictions = df[["ItemName", "StoreLocation"]].copy()
    test_predictions["Actual"] = y.map({0: "Not spoiled", 1: "Spoiled"})
    test_predictions["Predicted"] = pd.Series(oof_pred, index=df.index).map(
        {0: "Not spoiled", 1: "Spoiled"}
    )
    test_predictions["Predicted spoilage probability (%)"] = oof_prob * 100
    test_predictions["Correct"] = test_predictions["Actual"] == test_predictions["Predicted"]

    # Evaluate out-of-fold first; then fit the serving model on all labeled rows.
    model = make_model().fit(X, y)
    regression_model = make_regression_model().fit(X, regression_y)
    encoded_names = model.named_steps["preprocess"].get_feature_names_out()
    importance = pd.Series(
        model.named_steps["classifier"].feature_importances_, index=encoded_names
    ).sort_values(ascending=False)
    return (model, regression_model, feats, cat_options, num_info, metrics,
            regression_metrics, report, cm, test_predictions,
            regression_predictions, importance, len(df))


(model, regression_model, feats, cat_options, num_info, metrics, regression_metrics,
 report, cm, test_predictions, regression_predictions, importance, n_rows) = train_model(CSV_PATH)

st.markdown("<h1 style='text-align:center'>Spoilage Predictor</h1>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;opacity:0.7'>Enter a new inventory record for a spoilage prediction. "
    "Model performance below is measured separately with product names held out during evaluation.</p>",
    unsafe_allow_html=True,
)

st.markdown("<h3 style='text-align:center'>Enter a new inventory record</h3>", unsafe_allow_html=True)
with st.form("predict_form"):
    cols = st.columns(3)
    values = {}
    for i, c in enumerate(feats):
        with cols[i % 3]:
            if c in cat_options:
                values[c] = st.selectbox(c, cat_options[c])
            else:
                lo, hi, med, is_int = num_info[c]
                if is_int:
                    values[c] = st.number_input(c, min_value=int(lo), max_value=int(max(hi, lo + 1)),
                                                value=int(med), step=1)
                else:
                    values[c] = st.number_input(c, min_value=float(lo), max_value=float(max(hi, lo + 1)),
                                                value=float(med))
    submitted = st.form_submit_button("Calculate spoilage probability")

if submitted:
    row = pd.DataFrame([values])
    for c in cat_options:
        row[c] = row[c].astype("string")
    spoiled_class_index = list(model.classes_).index(1)
    prob = float(model.predict_proba(row)[0][spoiled_class_index])
    predicted_spoiled = int(model.predict(row)[0]) == 1

    if prob >= 0.7:
        level, advice = "HIGH", "Mark down or promote this item immediately, or move the stock."
    elif prob >= 0.4:
        level, advice = "MEDIUM", "Monitor closely and consider a discount if it does not move soon."
    else:
        level, advice = "LOW", "Normal handling is fine."

    st.markdown("---")
    st.subheader("Results for the new record")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Probability this record will spoil", f"{prob * 100:.2f}%")
    m2.metric("Predicted outcome", "Likely to spoil" if predicted_spoiled else "Unlikely to spoil")
    m3.metric("Risk level", level)
    m4.metric("Grouped CV accuracy", f"{metrics['accuracy'] * 100:.2f}%")
    predicted_waste_qty = max(0.0, float(regression_model.predict(row)[0]))
    m5.metric("Predicted wasted quantity", f"{predicted_waste_qty:.1f} units")
    st.progress(min(max(prob, 0.0), 1.0))
    st.caption("The spoilage percentage is the Random Forest's probability for this record. Grouped cross-validation accuracy measures performance on held-out product names; it cannot confirm whether one new record is correct before its real outcome is known.")
    st.markdown(f"<p style='text-align:center'><b>Suggested action:</b> {advice}</p>",
                unsafe_allow_html=True)

st.markdown("---")
a, b = st.columns(2)
with a:
    st.markdown("<h4 style='text-align:center'>Which inputs matter most</h4>", unsafe_allow_html=True)
    st.bar_chart(importance.head(10))
with b:
    st.markdown("<h4 style='text-align:center'>Model details</h4>", unsafe_allow_html=True)
    st.table(pd.DataFrame({
        "Item": ["Model", "Training data", "Evaluation method", "Excluded fields"],
        "Value": ["Random Forest (scikit-learn, 200 trees)", f"{n_rows:,} records",
                  "5-fold grouped CV by item name",
                  "Waste_Status, SpoilageChance, Waste_Qty, SuggestedAction, IDs and dates"],
    }))

st.markdown("---")
st.markdown("<h3 style='text-align:center'>Random Forest evaluation on unseen items</h3>", unsafe_allow_html=True)
st.caption("Five-fold stratified group cross-validation holds out each item name from training when its rows are evaluated. These out-of-fold predictions are separate from the serving model, which is then fitted on all records for new-item predictions.")
k1, k2, k3 = st.columns(3)
k1.metric("Accuracy", f"{metrics['accuracy'] * 100:.2f}%")
k2.metric("Balanced accuracy", f"{metrics['balanced_accuracy'] * 100:.2f}%")
k3.metric("ROC AUC", f"{metrics['roc_auc']:.3f}")
k4, k5, k6 = st.columns(3)
k4.metric("Precision · spoiled", f"{metrics['precision'] * 100:.2f}%")
k5.metric("Recall · spoiled", f"{metrics['recall'] * 100:.2f}%")
k6.metric("F1 · spoiled", f"{metrics['f1'] * 100:.2f}%")
st.markdown("#### Confusion matrix")
st.caption("Rows are actual labels; columns are model predictions.")
st.dataframe(pd.DataFrame(cm, index=["Actual: not spoiled", "Actual: spoiled"],
                          columns=["Predicted: not spoiled", "Predicted: spoiled"]),
             use_container_width=True)
st.markdown("#### Per-class classification report")
st.dataframe(pd.DataFrame(report).T.round(3), use_container_width=True)
st.markdown("#### Out-of-fold predictions (first 25 rows)")
st.dataframe(test_predictions.head(25), use_container_width=True, hide_index=True)

st.markdown("---")
st.markdown("<h3 style='text-align:center'>Regression evaluation: predict wasted quantity</h3>",
            unsafe_allow_html=True)
st.caption(
    "The regression target is Waste_Qty, measured in stock units. It is a derived "
    "project field: StockQty when the item spoiled, otherwise 0. The model excludes "
    "IsSpoiled and Waste_Qty from its inputs and uses the same five-fold, "
    "item-name-grouped evaluation, so each displayed prediction is for held-out items."
)
r1, r2, r3 = st.columns(3)
r1.metric("Mean Absolute Error (MAE)", f"{regression_metrics['mae']:.2f} units")
r2.metric("Root Mean Squared Error (RMSE)", f"{regression_metrics['rmse']:.2f} units")
r3.metric("R² score", f"{regression_metrics['r2']:.3f}")
with st.expander("How the regression metrics are calculated"):
    st.markdown(
        "- **MAE** = mean of `|actual Waste_Qty - predicted Waste_Qty|`; "
        "average error in stock units (lower is better).\n"
        "- **RMSE** = square root of the mean squared prediction error; also in "
        "stock units and penalizes larger misses more (lower is better).\n"
        "- **R²** = `1 - sum((actual - predicted)²) / sum((actual - mean(actual))²)`; "
        "1 is a perfect fit, 0 is no better than predicting the mean, and a negative "
        "value is worse than predicting the mean.\n\n"
        "Regression has no universal classification-style accuracy percentage. "
        "These values are calculated from out-of-fold predictions, not training-set predictions."
    )
st.markdown("#### Regression out-of-fold predictions (first 25 rows)")
st.dataframe(regression_predictions.head(25).round(2), use_container_width=True, hide_index=True)
