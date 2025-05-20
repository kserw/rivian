from flask import Flask, render_template, request, jsonify
import os
import requests
from dotenv import load_dotenv
import json # Keep json import
from datetime import datetime # Import datetime
import random # Import random module

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Ensure stats file path is absolute so it works regardless of the
# current working directory (useful in serverless environments).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATS_FILE = os.path.join(BASE_DIR, "rivian_stats.json")

# --- Helper Functions for Stats ---

def read_stats():
    """Reads stats from the JSON file. Creates it with defaults if missing."""
    default_stats = {
        "total_all_time": 0,
        "krystian_all_time": 0,
        "jensen_all_time": 0,
        "monthly": {
            # "YYYY-MM": {"krystian": 0, "jensen": 0, "total": 0}
        },
        "daily_max": {
            "date": None,
            "count": 0
        },
        # Track current day's count separately for simplicity
        "current_day": {
             "date": None,
             "count": 0
        }
    }
    try:
        with open(STATS_FILE, 'r') as f:
            stats = json.load(f)
            # Ensure all keys exist, merge with defaults
            for key, value in default_stats.items():
                if key not in stats:
                    stats[key] = value
                elif isinstance(value, dict): # Merge sub-dictionaries like monthly, daily_max etc
                     for sub_key, sub_value in value.items():
                         if sub_key not in stats[key]:
                             stats[key][sub_key] = sub_value
            return stats
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"File '{STATS_FILE}' not found or invalid. Creating with defaults.")
        # Write the defaults to create the file before returning them
        write_stats(default_stats)
        return default_stats # Return defaults if file missing or corrupt

def write_stats(stats_data):
    """Writes stats to the JSON file."""
    try:
        with open(STATS_FILE, 'w') as f:
            json.dump(stats_data, f, indent=4)
    except IOError as e:
        print(f"Error writing to stats file: {e}")

# --- End Helper Functions ---


# Alpaca API configuration
# Load keys for both users
KRYSTIAN_KEY = os.getenv('KRYSTIAN_APCA_API_KEY_ID')
KRYSTIAN_SECRET = os.getenv('KRYSTIAN_APCA_API_SECRET_KEY')
JENSEN_KEY = os.getenv('JENSEN_APCA_API_KEY_ID')
JENSEN_SECRET = os.getenv('JENSEN_APCA_API_SECRET_KEY')

BASE_URL = "https://api.alpaca.markets"  # Live trading domain

@app.route('/', methods=['GET'])
def index():
    stats = read_stats()
    now = datetime.now()
    current_month_str = now.strftime("%Y-%m")

    # Get current month stats (handle if month doesn't exist yet)
    monthly_stats = stats.get("monthly", {}).get(current_month_str, {"krystian": 0, "jensen": 0, "total": 0})

    # Pass all required stats to the template
    template_data = {
        "total_all_time": stats.get("total_all_time", 0),
        "krystian_all_time": stats.get("krystian_all_time", 0),
        "jensen_all_time": stats.get("jensen_all_time", 0),
        "total_this_month": monthly_stats.get("total", 0),
        "krystian_this_month": monthly_stats.get("krystian", 0),
        "jensen_this_month": monthly_stats.get("jensen", 0),
        "most_in_a_day": stats.get("daily_max", {}).get("count", 0)
    }
    return render_template('index.html', **template_data)

# New route to retrieve the latest stats in JSON format so clients can
# sync counters across different browsers.
@app.route('/stats', methods=['GET'])
def get_stats():
    """Return current statistics as JSON."""
    stats = read_stats()
    now = datetime.now()
    current_month_str = now.strftime("%Y-%m")

    monthly_stats = stats.get("monthly", {}).get(
        current_month_str, {"krystian": 0, "jensen": 0, "total": 0}
    )

    response_data = {
        "total_all_time": stats.get("total_all_time", 0),
        "krystian_all_time": stats.get("krystian_all_time", 0),
        "jensen_all_time": stats.get("jensen_all_time", 0),
        "total_this_month": monthly_stats.get("total", 0),
        "krystian_this_month": monthly_stats.get("krystian", 0),
        "jensen_this_month": monthly_stats.get("jensen", 0),
        "most_in_a_day": stats.get("daily_max", {}).get("count", 0),
    }
    return jsonify(response_data)

@app.route('/buy_rivn', methods=['POST'])
def buy_rivn():
    try:
        req_data = request.get_json()
        user = req_data.get('user')

        if not user or user not in ['krystian', 'jensen']:
            return jsonify({'status': 'error', 'message': 'Invalid or missing user specified.'}), 400

        # Select API keys based on user
        if user == 'krystian':
            api_key = KRYSTIAN_KEY
            secret_key = KRYSTIAN_SECRET
        else: # user == 'jensen'
            api_key = JENSEN_KEY
            secret_key = JENSEN_SECRET

        if not api_key or not secret_key:
             return jsonify({
                 'status': 'error',
                 'message': f'API credentials not found for user: {user}'
             }), 400

        # Debug information (optional, can be refined)
        # env_status = debug_env() # Modify or remove if debug_env is removed
        # ... (rest of the debug checks might need adjustment)

        # Prepare the order data
        order_data = {
            "symbol": "RIVN",
            "notional": 1.00,  # $1 worth of stock
            "side": "buy",
            "type": "market",
            "time_in_force": "day"
        }

        # Prepare headers exactly as specified in the documentation
        headers = {
            "APCA-API-KEY-ID": api_key, # Use user-specific key
            "APCA-API-SECRET-KEY": secret_key # Use user-specific secret
        }

        # First, let's verify the account is accessible
        account_response = requests.get(
            f"{BASE_URL}/v2/account",
            headers=headers
        )

        # Print raw response for debugging
        print(f"Account Response Status: {account_response.status_code}")
        print(f"Account Response Text: {account_response.text}")

        if account_response.status_code != 200:
            try:
                error_data = account_response.json()
                return jsonify({
                    'status': 'error',
                    'message': f'Account verification failed: {error_data}',
                    'debug': {
                        'status_code': account_response.status_code,
                        # 'env_status': env_status # Adjust or remove
                    }
                }), 400
            except ValueError:
                return jsonify({
                    'status': 'error',
                    'message': f'Account verification failed with status {account_response.status_code}. Response: {account_response.text}',
                    'debug': {
                        'status_code': account_response.status_code,
                        # 'env_status': env_status # Adjust or remove
                    }
                }), 400

        # If account verification succeeds, proceed with the order
        response = requests.post(
            f"{BASE_URL}/v2/orders",
            json=order_data,
            headers=headers
        )

        # Print raw response for debugging
        print(f"Order Response Status: {response.status_code}")
        print(f"Order Response Text: {response.text}")

        if response.status_code == 200:
            try:
                order = response.json()

                # ---- UPDATE STATS ----
                stats = read_stats()
                now = datetime.now()
                today_str = now.strftime("%Y-%m-%d")
                current_month_str = now.strftime("%Y-%m")

                # Update all-time totals
                stats["total_all_time"] = stats.get("total_all_time", 0) + 1
                if user == 'krystian':
                    stats["krystian_all_time"] = stats.get("krystian_all_time", 0) + 1
                else:
                    stats["jensen_all_time"] = stats.get("jensen_all_time", 0) + 1

                # Update monthly totals
                if current_month_str not in stats["monthly"]:
                    stats["monthly"][current_month_str] = {"krystian": 0, "jensen": 0, "total": 0}

                month_data = stats["monthly"][current_month_str]
                month_data["total"] = month_data.get("total", 0) + 1
                if user == 'krystian':
                     month_data["krystian"] = month_data.get("krystian", 0) + 1
                else:
                     month_data["jensen"] = month_data.get("jensen", 0) + 1


                # Update daily tracking and daily max
                current_day_data = stats.get("current_day", {"date": None, "count": 0})
                if current_day_data.get("date") == today_str:
                    current_day_data["count"] += 1
                else:
                    # Reset for the new day
                    current_day_data["date"] = today_str
                    current_day_data["count"] = 1
                stats["current_day"] = current_day_data # Store updated daily count

                # Check against daily max
                daily_max_data = stats.get("daily_max", {"date": None, "count": 0})
                if current_day_data["count"] > daily_max_data.get("count", 0):
                    stats["daily_max"]["date"] = today_str
                    stats["daily_max"]["count"] = current_day_data["count"]

                write_stats(stats)
                # ---- END UPDATE STATS ----

                # --- Random Success Message ---
                success_messages = [
                    "YOU JUST BOUGHT A DOLLA OF RIVN LFGGGGG",
                    "Order complete, see you at the moon",
                    "ik that rivian was sexy af. order confirmed."
                ]
                random_message = random.choice(success_messages)

                # Prepare response data for the frontend
                response_data = {
                    'status': 'success',
                    'message': random_message, # Use the random message
                    'user_new_all_time_count': stats[f'{user}_all_time'], # Add specific user's new count
                    'updated_stats': { # Send all updated stats needed by the frontend
                         "total_all_time": stats["total_all_time"],
                         "krystian_all_time": stats["krystian_all_time"],
                         "jensen_all_time": stats["jensen_all_time"],
                         "total_this_month": month_data["total"],
                         "krystian_this_month": month_data["krystian"],
                         "jensen_this_month": month_data["jensen"],
                         "most_in_a_day": stats["daily_max"]["count"]
                    }
                }
                return jsonify(response_data)

            except ValueError: # Handle case where order success response is not valid JSON
                 return jsonify({'status': 'error', 'message': f'Success response but invalid JSON: {response.text}'}), 400
            except Exception as e: # Catch potential errors during stats update
                print(f"Error updating stats: {e}")
                # Still return success for the order, but maybe log the stats error
                return jsonify({
                    'status': 'success', # Order was still placed
                    'message': f'Order submitted successfully. Order ID: {order.get("id", "N/A")}. (Stats update failed)',
                    'updated_stats': None # Indicate stats didn't update
                })

        else:
            try:
                error_response = response.json()
                # Check for specific insufficient buying power error
                if response.status_code == 403 and error_response.get('code') == 40310000 and 'insufficient buying power' in error_response.get('message', '').lower():
                    return jsonify({
                        'status': 'error',
                        'message': 'you have no money in your account broke mf 😂'
                    }), 403 # Return 403 status code as well
                
                # Otherwise, return the generic API error
                return jsonify({
                    'status': 'error',
                    'message': f'API Error: {error_response}',
                    'debug': {
                        'status_code': response.status_code,
                        # 'env_status': env_status # Adjust or remove
                    }
                }), 400
            except ValueError:
                return jsonify({
                    'status': 'error',
                    'message': f'API Error with status {response.status_code}. Response: {response.text}',
                    'debug': {
                        'status_code': response.status_code,
                        # 'env_status': env_status # Adjust or remove
                    }
                }), 400

    except Exception as e:
        print(f"Unhandled exception in /buy_rivn: {e}") # Log the error
        import traceback
        traceback.print_exc() # Print stack trace for debugging
        return jsonify({'status': 'error', 'message': f'An internal server error occurred: {str(e)}'}), 500

# For local development
if __name__ == '__main__':
    app.run(debug=True)

# For Vercel
app = app 