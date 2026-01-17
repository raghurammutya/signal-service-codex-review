"""
Clustering and Advanced Peak Detection Indicators

Machine learning-based clustering and topology-based peak detection.

Features:
- DBSCAN clustering for support/resistance levels
- K-means price level clustering
- Outlier detection
- Persistent homology peak detection (findpeaks)

Libraries: scikit-learn (installed), findpeaks
"""
import logging
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from sklearn.cluster import DBSCAN, KMeans
from sklearn.ensemble import IsolationForest

from app.services.indicator_registry import (
    register_indicator,
    IndicatorCategory
)

logger = logging.getLogger(__name__)

# Try to import findpeaks
try:
    from findpeaks import findpeaks
    FINDPEAKS_AVAILABLE = True
    logger.info("findpeaks library loaded successfully")
except ImportError:
    FINDPEAKS_AVAILABLE = False
    logger.warning("findpeaks not available - Advanced peak indicators will use fallback")


@register_indicator(
    name="cluster_support_resistance",
    category=IndicatorCategory.CLUSTERING,
    library="scikit-learn",
    description="DBSCAN clustering of swing points into support/resistance zones",
    parameters={"eps": 0.02, "min_samples": 2},
    output_type="dataframe"
)
def cluster_support_resistance(
    df: pd.DataFrame,
    eps: float = 0.02,
    min_samples: int = 2,
    **kwargs
) -> pd.DataFrame:
    """
    Cluster nearby support/resistance levels using DBSCAN.

    Groups swing highs and lows into significant zones.

    Args:
        df: DataFrame with OHLCV data
        eps: Maximum distance between points (2% of price default)
        min_samples: Minimum points to form cluster

    Returns:
        DataFrame with level, type, touches, strength, std
    """
    try:
        # Extract swing points (simple high/low detection)
        swing_highs = []
        swing_lows = []

        for i in range(2, len(df) - 2):
            # Swing high
            if (df['high'].iloc[i] > df['high'].iloc[i-1] and
                df['high'].iloc[i] > df['high'].iloc[i-2] and
                df['high'].iloc[i] > df['high'].iloc[i+1] and
                df['high'].iloc[i] > df['high'].iloc[i+2]):
                swing_highs.append(df['high'].iloc[i])

            # Swing low
            if (df['low'].iloc[i] < df['low'].iloc[i-1] and
                df['low'].iloc[i] < df['low'].iloc[i-2] and
                df['low'].iloc[i] < df['low'].iloc[i+1] and
                df['low'].iloc[i] < df['low'].iloc[i+2]):
                swing_lows.append(df['low'].iloc[i])

        if not swing_highs and not swing_lows:
            return pd.DataFrame(columns=['level', 'type', 'touches', 'strength', 'std'])

        # Cluster resistance levels (swing highs)
        resistance_clusters = _cluster_levels(swing_highs, eps, min_samples, 'resistance')

        # Cluster support levels (swing lows)
        support_clusters = _cluster_levels(swing_lows, eps, min_samples, 'support')

        # Combine and sort by strength
        all_clusters = resistance_clusters + support_clusters
        result_df = pd.DataFrame(all_clusters)

        if not result_df.empty:
            result_df = result_df.sort_values('strength', ascending=False).reset_index(drop=True)

        return result_df

    except Exception as e:
        logger.exception(f"Error clustering support/resistance: {e}")
        return pd.DataFrame(columns=['level', 'type', 'touches', 'strength', 'std'])


def _cluster_levels(
    levels: List[float],
    eps: float,
    min_samples: int,
    level_type: str
) -> List[Dict]:
    """Helper function to cluster price levels"""
    if len(levels) < min_samples:
        return []

    X = np.array(levels).reshape(-1, 1)
    mean_price = np.mean(levels)

    # DBSCAN clustering
    clustering = DBSCAN(eps=eps * mean_price, min_samples=min_samples)
    labels = clustering.fit_predict(X)

    # Extract clusters
    clusters = []
    for label in set(labels):
        if label == -1:  # Noise
            continue

        cluster_points = X[labels == label].flatten()
        clusters.append({
            'level': float(np.mean(cluster_points)),
            'type': level_type,
            'touches': len(cluster_points),
            'strength': min(1.0, len(cluster_points) / (min_samples * 3)),
            'std': float(np.std(cluster_points))
        })

    return clusters


@register_indicator(
    name="kmeans_price_levels",
    category=IndicatorCategory.CLUSTERING,
    library="scikit-learn",
    description="K-means clustering to identify N most important price levels",
    parameters={"n_clusters": 5},
    output_type="dataframe"
)
def kmeans_price_levels(
    df: pd.DataFrame,
    n_clusters: int = 5,
    **kwargs
) -> pd.DataFrame:
    """
    Use K-means to identify the N most important price levels.

    Finds natural price zones where trading activity clusters.

    Args:
        df: DataFrame with OHLCV data
        n_clusters: Number of price levels to identify

    Returns:
        DataFrame with level, volume_weight, inertia columns
    """
    try:
        # Create price samples weighted by volume
        prices = []
        weights = []

        for _, row in df.iterrows():
            typical_price = (row['high'] + row['low'] + row['close']) / 3
            prices.append(typical_price)
            weights.append(row['volume'])

        X = np.array(prices).reshape(-1, 1)
        weights = np.array(weights)

        # K-means clustering
        kmeans = KMeans(n_clusters=min(n_clusters, len(df)), random_state=42, n_init=10)
        kmeans.fit(X, sample_weight=weights)

        # Get cluster centers and their properties
        centers = kmeans.cluster_centers_.flatten()
        labels = kmeans.labels_

        # Calculate volume at each level
        level_volumes = []
        for i in range(len(centers)):
            mask = labels == i
            level_volume = float(np.sum(weights[mask]))
            level_volumes.append(level_volume)

        # Create result DataFrame
        result_df = pd.DataFrame({
            'level': centers,
            'volume_weight': level_volumes,
            'inertia': kmeans.inertia_ / len(centers)
        })

        # Sort by volume weight
        result_df = result_df.sort_values('volume_weight', ascending=False).reset_index(drop=True)

        return result_df

    except Exception as e:
        logger.exception(f"Error calculating K-means levels: {e}")
        return pd.DataFrame(columns=['level', 'volume_weight', 'inertia'])


@register_indicator(
    name="price_outliers",
    category=IndicatorCategory.CLUSTERING,
    library="scikit-learn",
    description="Detect anomalous price moves using Isolation Forest - identifies unusual spikes",
    parameters={"contamination": 0.1},
    output_type="series"
)
def price_outliers(
    df: pd.DataFrame,
    contamination: float = 0.1,
    **kwargs
) -> pd.Series:
    """
    Detect price outliers using Isolation Forest.

    Identifies anomalous price moves that deviate from normal patterns.
    Useful for detecting pump/dump, news events, etc.

    Args:
        df: DataFrame with OHLCV data
        contamination: Expected proportion of outliers (0.1 = 10%)

    Returns:
        Series with 1 for outliers, 0 for normal points
    """
    try:
        # Create features: price change %, volume change %, range %
        features = []

        for i in range(1, len(df)):
            price_change_pct = (df['close'].iloc[i] - df['close'].iloc[i-1]) / df['close'].iloc[i-1] * 100
            volume_change_pct = (df['volume'].iloc[i] - df['volume'].iloc[i-1]) / (df['volume'].iloc[i-1] + 1) * 100
            range_pct = (df['high'].iloc[i] - df['low'].iloc[i]) / df['close'].iloc[i] * 100

            features.append([price_change_pct, volume_change_pct, range_pct])

        if len(features) < 2:
            return pd.Series(0, index=df.index)

        X = np.array(features)

        # Isolation Forest
        iso_forest = IsolationForest(contamination=contamination, random_state=42)
        predictions = iso_forest.fit_predict(X)

        # Convert to binary (1 = outlier, 0 = normal)
        result = pd.Series(0, index=df.index)
        result.iloc[1:] = (predictions == -1).astype(int)

        return result

    except Exception as e:
        logger.exception(f"Error detecting outliers: {e}")
        return pd.Series(0, index=df.index)


@register_indicator(
    name="persistent_peaks",
    category=IndicatorCategory.ADVANCED_PEAKS,
    library="findpeaks",
    description="Topology-based peak detection using persistent homology - noise-resistant",
    parameters={"method": "topology", "lookahead": 1},
    output_type="dataframe"
)
def persistent_peaks(
    df: pd.DataFrame,
    method: str = "topology",
    lookahead: int = 1,
    **kwargs
) -> pd.DataFrame:
    """
    Find peaks using persistent homology (topology-based).

    More robust than simple peak detection - focuses on persistent features.
    Excellent for noisy data.

    Args:
        df: DataFrame with OHLCV data
        method: 'topology' for persistent homology, 'peakdetect' for standard
        lookahead: Distance to look ahead for peak confirmation

    Returns:
        DataFrame with index, price, persistence columns
    """
    try:
        if not FINDPEAKS_AVAILABLE:
            from app.errors import ComputationError
            raise ComputationError("findpeaks library not available - advanced peak detection requires findpeaks library")

        fp = findpeaks(method=method, lookahead=lookahead, verbose=0)

        prices = df['high'].values
        results = fp.fit(prices)

        if 'Xdetect' not in results or len(results['Xdetect']) == 0:
            return pd.DataFrame(columns=['index', 'timestamp', 'price', 'persistence'])

        # Extract peaks
        peak_indices = results['Xdetect']
        persistence = results.get('persistence', [1.0] * len(peak_indices))

        peak_df = pd.DataFrame({
            'index': peak_indices,
            'timestamp': [df.index[i] for i in peak_indices],
            'price': prices[peak_indices],
            'persistence': persistence
        })

        # Sort by persistence (most significant first)
        peak_df = peak_df.sort_values('persistence', ascending=False).reset_index(drop=True)

        return peak_df

    except Exception as e:
        from app.errors import ComputationError
        logger.exception(f"Error in persistent peak detection: {e}")
        raise ComputationError(f"Failed to compute persistent peaks: {e}") from e


@register_indicator(
    name="persistent_valleys",
    category=IndicatorCategory.ADVANCED_PEAKS,
    library="findpeaks",
    description="Topology-based valley/trough detection using persistent homology",
    parameters={"method": "topology", "lookahead": 1},
    output_type="dataframe"
)
def persistent_valleys(
    df: pd.DataFrame,
    method: str = "topology",
    lookahead: int = 1,
    **kwargs
) -> pd.DataFrame:
    """
    Find valleys using persistent homology.

    Args:
        df: DataFrame with OHLCV data
        method: Detection method
        lookahead: Distance for confirmation

    Returns:
        DataFrame with valley information
    """
    try:
        if not FINDPEAKS_AVAILABLE:
            from app.errors import ComputationError
            raise ComputationError("findpeaks library not available - advanced valley detection requires findpeaks library")

        fp = findpeaks(method=method, lookahead=lookahead, verbose=0)

        # Invert prices to find valleys
        prices = -df['low'].values
        results = fp.fit(prices)

        if 'Xdetect' not in results or len(results['Xdetect']) == 0:
            return pd.DataFrame(columns=['index', 'timestamp', 'price', 'persistence'])

        # Extract valleys
        valley_indices = results['Xdetect']
        persistence = results.get('persistence', [1.0] * len(valley_indices))

        valley_df = pd.DataFrame({
            'index': valley_indices,
            'timestamp': [df.index[i] for i in valley_indices],
            'price': df['low'].values[valley_indices],  # Use original (not inverted)
            'persistence': persistence
        })

        # Sort by persistence
        valley_df = valley_df.sort_values('persistence', ascending=False).reset_index(drop=True)

        return valley_df

    except Exception as e:
        from app.errors import ComputationError
        logger.exception(f"Error in persistent valley detection: {e}")
        raise ComputationError(f"Failed to compute persistent valleys: {e}") from e


@register_indicator(
    name="peaks_ranked_by_persistence",
    category=IndicatorCategory.ADVANCED_PEAKS,
    library="findpeaks",
    description="All peaks ranked by persistence score - identifies most significant swings",
    parameters={"min_persistence": 0.1},
    output_type="dataframe"
)
def peaks_ranked_by_persistence(
    df: pd.DataFrame,
    min_persistence: float = 0.1,
    **kwargs
) -> pd.DataFrame:
    """
    Find all peaks and rank by persistence score.

    Returns only peaks above minimum persistence threshold.

    Args:
        df: DataFrame with OHLCV data
        min_persistence: Minimum persistence score (0-1)

    Returns:
        DataFrame with peaks ranked by significance
    """
    try:
        if not FINDPEAKS_AVAILABLE:
            from app.errors import ComputationError
            raise ComputationError("findpeaks library not available - peak ranking requires findpeaks library")

        peaks_df = persistent_peaks(df, method='topology')

        if peaks_df.empty:
            return peaks_df

        # Filter by minimum persistence
        peaks_df = peaks_df[peaks_df['persistence'] >= min_persistence]

        # Already sorted by persistence (done in persistent_peaks)
        return peaks_df

    except Exception as e:
        from app.errors import ComputationError
        logger.exception(f"Error ranking peaks by persistence: {e}")
        raise ComputationError(f"Failed to rank peaks by persistence: {e}") from e


# Note: Mock functions removed - production code must handle missing dependencies properly
# by raising ComputationError when findpeaks library is not available
