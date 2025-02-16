import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from datetime import datetime
import json

class F1Dashboard:
    def __init__(self):
        self.base_url = 'http://ergast.com/api/f1'
        st.set_page_config(
            page_title="F1 Dashboard",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        
        # Initialize session state for persistent storage
        if 'selected_drivers' not in st.session_state:
            st.session_state.selected_drivers = []
        if 'selected_constructors' not in st.session_state:
            st.session_state.selected_constructors = []
        if 'comparison_mode' not in st.session_state:
            st.session_state.comparison_mode = False
        if 'dark_mode' not in st.session_state:
            st.session_state.dark_mode = False

    def fetch_data(self, endpoint, offset=0, limit=1000):
        """Fetch data from Ergast API with pagination and caching"""
        @st.cache_data(ttl=3600)  # Cache data for 1 hour
        def fetch_cached(url):
            try:
                response = requests.get(url)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                st.error(f"Error fetching data: {str(e)}")
                return None
            
        url = f"{self.base_url}/{endpoint}.json?limit={limit}&offset={offset}"
        return fetch_cached(url)

    def get_seasons_list(self):
        """Get list of F1 seasons with error handling"""
        try:
            data = self.fetch_data('seasons', limit=100)
            if data and 'MRData' in data and 'SeasonTable' in data['MRData']:
                seasons = data['MRData']['SeasonTable']['Seasons']
                return sorted([season['season'] for season in seasons], reverse=True)
            else:
                st.error("Unable to fetch seasons data. Please try again later.")
                return ["2023"]
        except Exception as e:
            st.error(f"Error getting seasons list: {str(e)}")
            return ["2023"]

    def get_season_results(self, year):
        """Get race results for a specific season with pagination"""
        all_results = []
        offset = 0
        limit = 100
        
        while True:
            data = self.fetch_data(f'{year}/results', offset=offset, limit=limit)
            if not data or 'MRData' not in data or 'RaceTable' not in data['MRData']:
                break
                
            races = data['MRData']['RaceTable']['Races']
            if not races:
                break
                
            for race in races:
                race_name = race['raceName']
                round_num = int(race['round'])
                race_date = race['date']
                
                for result in race['Results']:
                    position = result.get('position', 'DNF')
                    position = int(position) if position.isdigit() else None
                    
                    try:
                        points = float(result.get('points', 0))
                    except (ValueError, TypeError):
                        points = 0
                    
                    all_results.append({
                        'round': round_num,
                        'race': race_name,
                        'date': race_date,
                        'driver': f"{result['Driver']['givenName']} {result['Driver']['familyName']}",
                        'constructor': result['Constructor']['name'],
                        'position': position,
                        'points': points,
                        'status': result.get('status', '')
                    })
            
            offset += limit
            total = int(data['MRData']['total'])
            if offset >= total:
                break
                
        if not all_results:
            st.warning(f"No results found for season {year}")
            return pd.DataFrame()
            
        df = pd.DataFrame(all_results)
        df['date'] = pd.to_datetime(df['date'])
        return df.sort_values(['round', 'position'])

    def create_driver_standings_chart(self, df):
        """Create cumulative points chart for drivers"""
        df_sorted = df.sort_values(['date', 'round'])
        df_cumsum = df_sorted.pivot_table(
            index=['round', 'race'],
            columns='driver',
            values='points',
            aggfunc='sum'
        ).cumsum()
        
        fig = go.Figure()
        for driver in df_cumsum.columns:
            fig.add_trace(go.Scatter(
                x=df_cumsum.index.get_level_values('race'),
                y=df_cumsum[driver],
                name=driver,
                mode='lines+markers'
            ))
        
        fig.update_layout(
            title='Driver Points Progression Through Season',
            xaxis_title='Race',
            yaxis_title='Cumulative Points',
            height=600,
            showlegend=True,
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=1.05
            )
        )
        return fig

    def create_constructor_performance_chart(self, df):
        """Create constructor performance chart"""
        constructor_points = df.groupby('constructor')['points'].sum().sort_values(ascending=True)
        
        fig = px.bar(
            constructor_points,
            orientation='h',
            title='Constructor Performance',
            labels={'value': 'Total Points', 'constructor': 'Constructor'},
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        fig.update_layout(height=400)
        return fig

    def create_podium_finishes_chart(self, df):
        """Create podium finishes chart"""
        podium_counts = df[df['position'].between(1, 3)]['driver'].value_counts()
        
        fig = px.pie(
            values=podium_counts.values,
            names=podium_counts.index,
            title='Podium Finishes Distribution',
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        fig.update_layout(height=400)
        return fig

    def show_constructor_comparison(self, df):
        """Show detailed constructor comparison stats with visualizations"""
        st.subheader("Constructor Comparison")
        
        # Calculate comparison metrics
        comparison_metrics = df.groupby('constructor').agg({
            'points': ['sum', 'mean'],
            'position': ['mean', 'min'],
            'race': 'count'
        }).round(2)
        
        # Display metrics table
        st.dataframe(comparison_metrics)
        
        # Create visualization tabs
        tab1, tab2, tab3 = st.tabs(["Points Progression", "Average Positions", "Performance Distribution"])
        
        with tab1:
            # Points progression through the season
            points_prog = df.pivot_table(
                index='round',
                columns='constructor',
                values='points',
                aggfunc='sum'
            ).cumsum()
            
            fig = px.line(
                points_prog,
                title="Constructor Points Progression",
                labels={'value': 'Cumulative Points', 'round': 'Race Round'},
                markers=True
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            # Average position by race
            avg_pos = df.pivot_table(
                index='race',
                columns='constructor',
                values='position',
                aggfunc='mean'
            )
            
            fig = px.line(
                avg_pos,
                title="Average Race Positions",
                labels={'value': 'Position (Lower is Better)', 'race': 'Race'},
                markers=True
            )
            # Invert y-axis since lower position is better
            fig.update_layout(yaxis={'autorange': 'reversed'})
            st.plotly_chart(fig, use_container_width=True)
        
        with tab3:
            # Box plot of race positions
            fig = px.box(
                df,
                x='constructor',
                y='position',
                title="Race Positions Distribution",
                labels={'position': 'Race Position', 'constructor': 'Constructor'}
            )
            # Invert y-axis since lower position is better
            fig.update_layout(yaxis={'autorange': 'reversed'})
            st.plotly_chart(fig, use_container_width=True)

    def show_driver_comparison(self, df, drivers):
        """Show head-to-head driver comparison with visualizations"""
        st.subheader("Driver Head-to-Head")
        
        # Calculate driver statistics
        driver_stats = []
        for driver in drivers:
            driver_df = df[df['driver'] == driver]
            stats = {
                'Driver': driver,
                'Points': driver_df['points'].sum(),
                'Avg Position': round(driver_df['position'].mean(), 2),
                'Podiums': len(driver_df[driver_df['position'] <= 3]),
                'Races': len(driver_df),
                'Wins': len(driver_df[driver_df['position'] == 1])
            }
            driver_stats.append(stats)
        
        comparison_df = pd.DataFrame(driver_stats)
        
        # Create visualization tabs
        tab1, tab2, tab3 = st.tabs(["Overview", "Race Performance", "Points Progression"])
        
        with tab1:
            # Radar chart comparing key metrics
            metrics = ['Points', 'Podiums', 'Wins', 'Avg Position']
            
            fig = go.Figure()
            
            for driver in drivers:
                driver_data = comparison_df[comparison_df['Driver'] == driver].iloc[0]
                
                fig.add_trace(go.Scatterpolar(
                    r=[driver_data['Points'], 
                        driver_data['Podiums'] * 20,  # Scale podiums for better visualization
                        driver_data['Wins'] * 25,     # Scale wins for better visualization
                        100 - driver_data['Avg Position'] * 5],  # Invert position for better visualization
                    theta=metrics,
                    fill='toself',
                    name=driver
                ))
            
            fig.update_layout(
                polar=dict(
                    radialaxis=dict(
                        visible=True,
                        range=[0, max([
                            comparison_df['Points'].max(),
                            comparison_df['Podiums'].max() * 20,
                            comparison_df['Wins'].max() * 25,
                            100
                        ])]
                    )),
                showlegend=True,
                title="Driver Performance Comparison"
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Display stats table
            st.dataframe(comparison_df)
        
        with tab2:
            # Race position comparison
            race_positions = df[df['driver'].isin(drivers)].pivot(
                index='race',
                columns='driver',
                values='position'
            )
            
            fig = px.line(
                race_positions,
                title="Race Positions Comparison",
                labels={'value': 'Position', 'race': 'Race'},
                markers=True
            )
            # Invert y-axis since lower position is better
            fig.update_layout(yaxis={'autorange': 'reversed'})
            st.plotly_chart(fig, use_container_width=True)
        
        with tab3:
            # Points progression
            points_prog = df[df['driver'].isin(drivers)].pivot_table(
                index='round',
                columns='driver',
                values='points',
                aggfunc='sum'
            ).cumsum()
            
            fig = px.line(
                points_prog,
                title="Points Progression Through Season",
                labels={'value': 'Cumulative Points', 'round': 'Race Round'},
                markers=True
            )
            st.plotly_chart(fig, use_container_width=True)

    def display_kpi_cards(self, df):
        """Display interactive KPI cards"""
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_races = len(df['race'].unique())
            st.metric(
                "Total Races",
                total_races,
                help="Total number of races in the selected season"
            )
            
        with col2:
            total_drivers = len(df['driver'].unique())
            st.metric(
                "Total Drivers",
                total_drivers,
                help="Number of drivers who participated"
            )
            
        with col3:
            total_constructors = len(df['constructor'].unique())
            st.metric(
                "Total Constructors",
                total_constructors,
                help="Number of constructor teams"
            )
            
        with col4:
            points_leader = df.groupby('driver')['points'].sum().idxmax()
            points = int(df.groupby('driver')['points'].sum().max())
            st.metric(
                "Points Leader",
                points_leader,
                f"{points} pts",
                help="Driver with the most points"
            )

    def create_sidebar(self):
        """Create interactive sidebar with working filters"""
        st.sidebar.title("Dashboard Controls")
        
        # Season Selection
        seasons = self.get_seasons_list()
        selected_season = st.sidebar.selectbox(
            "Select Season",
            seasons,
            help="Choose a Formula 1 season to analyze"
        )
        
        # Comparison Mode
        st.sidebar.toggle("Enable Comparison Mode", key="comparison_mode")
        
        # Advanced Filters Section
        st.sidebar.subheader("Advanced Filters")
        
        filters = {}
        
        filter_options = st.sidebar.expander("Filter Options", expanded=False)
        with filter_options:
            # Points Range Filter
            points_range = st.slider(
                "Filter by Points Range",
                min_value=0,
                max_value=400,
                value=(0, 400)
            )
            filters['points_range'] = points_range
            
            # Race Selection
            if 'current_df' in st.session_state:
                available_races = sorted(st.session_state.current_df['race'].unique())
                selected_races = st.multiselect(
                    "Select Specific Races",
                    available_races,
                    default=available_races
                )
                filters['selected_races'] = selected_races
            
            # Position Filter
            position_range = st.slider(
                "Filter by Position Range",
                min_value=1,
                max_value=20,
                value=(1, 20)
            )
            filters['position_range'] = position_range
            
            # Constructor Filter
            if 'current_df' in st.session_state:
                available_constructors = sorted(st.session_state.current_df['constructor'].unique())
                selected_constructors = st.multiselect(
                    "Select Constructors",
                    available_constructors,
                    default=available_constructors
                )
                filters['selected_constructors'] = selected_constructors

        return selected_season, filters


    def apply_filters(self, df, filters):
        """Apply all filters to the DataFrame"""
        filtered_df = df.copy()
        
        # Apply points range filter
        if 'points_range' in filters:
            min_points, max_points = filters['points_range']
            filtered_df = filtered_df[filtered_df['points'].between(min_points, max_points)]
        
        # Apply race filter
        if 'selected_races' in filters and filters['selected_races']:
            filtered_df = filtered_df[filtered_df['race'].isin(filters['selected_races'])]
        
        # Apply position filter
        if 'position_range' in filters:
            min_pos, max_pos = filters['position_range']
            # Only filter where position is not None (handles DNF, DSQ etc.)
            position_mask = (filtered_df['position'].notna()) & \
                          (filtered_df['position'].between(min_pos, max_pos))
            filtered_df = filtered_df[position_mask]
        
        # Apply constructor filter
        if 'selected_constructors' in filters and filters['selected_constructors']:
            filtered_df = filtered_df[filtered_df['constructor'].isin(filters['selected_constructors'])]
        
        return filtered_df


    def create_interactive_charts(self, df, points_range):
        """Create and display interactive charts"""
        # Driver Standings Chart
        driver_fig = self.create_driver_standings_chart(df)
        st.plotly_chart(driver_fig, use_container_width=True)
        
        # Two-column layout for secondary charts
        col1, col2 = st.columns(2)
        
        with col1:
            constructor_fig = self.create_constructor_performance_chart(df)
            st.plotly_chart(constructor_fig, use_container_width=True)
            
            if st.session_state.comparison_mode:
                selected_constructors = st.multiselect(
                    "Compare Constructors",
                    df['constructor'].unique(),
                    key="constructor_comparison"
                )
                if selected_constructors:
                    comparison_df = df[df['constructor'].isin(selected_constructors)]
                    self.show_constructor_comparison(comparison_df)
        
        with col2:
            podium_fig = self.create_podium_finishes_chart(df)
            st.plotly_chart(podium_fig, use_container_width=True)
            
            if st.session_state.comparison_mode:
                selected_drivers = st.multiselect(
                    "Compare Drivers Head-to-Head",
                    df['driver'].unique(),
                    key="driver_comparison"
                )
                if len(selected_drivers) == 2:
                    self.show_driver_comparison(df, selected_drivers)

    def run(self):
        """Main dashboard application with working filters"""
        # Custom CSS for better visual hierarchy
        st.markdown("""
            <style>
                .block-container {padding-top: 1rem;}
                .element-container {margin-bottom: 1rem;}
                .stMetric {background-color: #f0f2f6; padding: 1rem; border-radius: 0.5rem;}
            </style>
        """, unsafe_allow_html=True)
        
        # Dashboard Header
        st.title("Formula 1 Season Analysis Dashboard")
        
        # Get filters from sidebar
        selected_season, filters = self.create_sidebar()
        
        # Main dashboard content
        with st.spinner(f'Loading {selected_season} season data...'):
            df = self.get_season_results(selected_season)
            
            if not df.empty:
                # Store the original dataset for filter options
                st.session_state.current_df = df
                
                # Apply filters to the data
                filtered_df = self.apply_filters(df, filters)
                
                if filtered_df.empty:
                    st.warning("No data matches the selected filters. Please adjust your filter criteria.")
                    return
                
                # Show active filters
                if st.sidebar.checkbox("Show Active Filters"):
                    st.sidebar.write("Active Filters:")
                    for filter_name, filter_value in filters.items():
                        st.sidebar.write(f"- {filter_name}: {filter_value}")
                
                # Interactive KPI Cards
                self.display_kpi_cards(filtered_df)
                
                # Create and display interactive charts
                self.create_interactive_charts(filtered_df, filters.get('points_range', (0, 400)))
                
                # Add data exploration section
                with st.expander("Explore Raw Data"):
                    st.dataframe(filtered_df)
                    
                    # Add export functionality
                    csv = filtered_df.to_csv(index=False)
                    st.download_button(
                        "Download Data as CSV",
                        csv,
                        f"f1_{selected_season}_filtered_data.csv",
                        "text/csv"
                    )
            else:
                st.warning("No data available for the selected season. Please try another season or check your internet connection.")

if __name__ == "__main__":
    dashboard = F1Dashboard()
    dashboard.run()