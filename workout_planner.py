import streamlit as st
import pandas as pd
import re
from ortools.sat.python import cp_model
from itertools import permutations

global original_df
global muscle_bounds
original_df = pd.read_csv('exercises_cleaned.csv')
muscle_bounds = pd.read_csv('muscle_bounds.csv')


@st.cache_data(persist=True)
def read_and_filter(filename, muscle_groups):
    df = pd.read_csv(filename)
    filtered = df[df['major_muscle'].isin(muscle_groups)]
    if filtered.empty:
        filtered = df[df['minor_muscle'].isin(muscle_groups)]

    # Can be removed, just ensuring that there is no bias in the selection
    shuffled = filtered.sample(frac=1).reset_index(drop=True)
    return shuffled


def create_problem(df):
    model = cp_model.CpModel()

    exercise_vars = {}
    for _, row in df.iterrows():
        exercise_vars[row['exercise']] = model.NewBoolVar(row['exercise'])

    lower_bound, upper_bound = 3, 5
    model.Add(sum(exercise_vars.values()) >= lower_bound)
    model.Add(sum(exercise_vars.values()) <= upper_bound)

    return model, exercise_vars


def extract_and_add(**kwargs):
    all_muscles = []
    pattern = re.compile(r"'([^']+)'")

    for _, value in kwargs.items():
        matches = pattern.findall(value)
        for match in matches:
            all_muscles.append(match)
    return all_muscles


def get_all_muscles(exercise):
    row = original_df[original_df['exercise'] == exercise]
    target_muscles = row['target_muscles'].values[0]
    synergist_muscles = row['synergist_muscles'].values[0]
    stabilizer_muscles = row['stabilizer_muscles'].values[0]
    dynamic_stabilizer_muscles = row['dynamic_stabilizer_muscles'].values[0]
    antagonist_stabilizer_muscles = row['antagonist_stabilizer_muscles'].values[0]

    kwargs = {
        'target_muscles': target_muscles,
        'synergist_muscles': synergist_muscles,
        'stabilizer_muscles': stabilizer_muscles,
        'dynamic_stabilizer_muscles': dynamic_stabilizer_muscles,
        'antagonist_stabilizer_muscles':
        antagonist_stabilizer_muscles
    }
    all_muscles = extract_and_add(**kwargs)
    return all_muscles


def find_lowest_contributing_exercise(selected_workouts):
    contribution_set = set()
    contribution_set_sizes = []
    for exercise in selected_workouts:
        all_muscles = get_all_muscles(exercise)
        for muscle in all_muscles:
            contribution_set.add(muscle)
        contribution_set_sizes.append(len(contribution_set))

    differences = [contribution_set_sizes[i] - contribution_set_sizes[i - 1]
                   for i in range(1, len(contribution_set_sizes))]

    # Move the index by 1 to account for the difference calculation
    min_index = differences.index(min(differences)) + 1
    lowest_contributor = selected_workouts[min_index]
    total_muscles = len(contribution_set)
    return lowest_contributor, total_muscles


def get_most_common_lowest_contributor(all_permutations):
    contributors = {}
    for permutation in all_permutations:
        lowest_contributor, total_muscles = find_lowest_contributing_exercise(
            permutation)
        contributors[(lowest_contributor, total_muscles)] = contributors.get(
            lowest_contributor, 0) + 1
    return max(contributors, key=contributors.get)


def get_all_permutations(selected_workouts):
    all_permutations = []
    for permutation in permutations(selected_workouts):
        all_permutations.append(list(permutation))
    most_common = get_most_common_lowest_contributor(all_permutations)
    return most_common


def process_output(selected_workouts, df):
    rows = []

    for workout in selected_workouts:
        row = df[df['exercise'] == workout].copy()
        row['target_muscles'] = row['target_muscles'].str.title()
        rows.append(row)

    output = pd.concat(rows)

    # Select specific columns
    output = output[['exercise', 'target_muscles', 'mechanics']]
    output.reset_index(inplace=True, drop=True)
    output.index += 1
    return output


def get_bounds(exercise):
    row = original_df[original_df['exercise'] == exercise]
    target_muscles = row['minor_muscle'].values[0]
    bounds = muscle_bounds[muscle_bounds['Muscle'] == target_muscles]
    return bounds['Lower Bound'].sum(), bounds['Upper Bound'].sum()


def solve(model, exercise_vars, df):
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    output = None

    if status == cp_model.OPTIMAL:
        selected_workouts = [exercise for exercise,
                             var in exercise_vars.items() if solver.Value(var) == 1]

        most_common_lowest_contributor = get_all_permutations(
            selected_workouts)
        exercise = most_common_lowest_contributor[0]
        total_muscles = most_common_lowest_contributor[1]
        lower_bound, upper_bound = get_bounds(exercise)
        if not lower_bound <= total_muscles <= upper_bound:
            df = df[df['exercise'] != exercise]

            model, exercise_vars = create_problem(df)

            st.text(f"• Removed {exercise} from the workout")

            output = solve(model, exercise_vars, df)
        else:
            st.text(f"• Kept {exercise} in the workout")
            output = process_output(selected_workouts, df)
    return output


st.set_page_config(page_title="Workout Planner", page_icon="💪")

st.title("Plan your next workout intelligently")
muscle_groups = st.multiselect(
    "Select muscle groups for your workout",
    [
        "Neck",
        "Shoulders",
        "Upper Arms",
        "Forearms",
        "Back",
        "Chest",
        "Waist",
        "Hips",
        "Thighs",
        "Calves"
    ],
)

generate_button = st.button("Generate Workout")

if generate_button:
    with st.spinner("Generating your workout..."):
        # Create a dictionary to store results for each muscle group
        muscle_results = {}

        for muscle_group in muscle_groups:
            df = read_and_filter('exercises_cleaned.csv', [muscle_group])
            model, exercise_vars = create_problem(df)
            selected_workouts = solve(model, exercise_vars, df)

            if selected_workouts is not None:
                muscle_results[muscle_group] = selected_workouts

        if not muscle_results:
            st.write("No workout generated")
        else:
            st.write("#")

            # Concatenate all workout results into one DataFrame
            all_workouts = pd.concat(muscle_results.values(
            ), keys=muscle_results.keys(), names=['Muscle Group'])

            # Display the combined table
            st.write("## Here are the results! 🎉")
            columns_to_display = ['exercise', 'target_muscles', 'mechanics']
            filtered_workouts = all_workouts[columns_to_display]
            filtered_workouts.reset_index(
                inplace=True, drop=True)
            filtered_workouts.index += 1
            st.table(filtered_workouts)
