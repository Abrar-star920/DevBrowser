import requests
import sys
import json
from datetime import datetime

class DevBrowserAPITester:
    def __init__(self, base_url="https://codesafeview.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.created_items = {
            'bookmarks': [],
            'history': [],
            'tabs': []
        }

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    if isinstance(response_data, dict) and 'id' in response_data:
                        print(f"   Response ID: {response_data['id']}")
                    return True, response_data
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_detail = response.json()
                    print(f"   Error: {error_detail}")
                except:
                    print(f"   Response: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_root_endpoint(self):
        """Test root API endpoint"""
        success, response = self.run_test(
            "Root API Endpoint",
            "GET",
            "",
            200
        )
        return success

    def test_url_analysis(self):
        """Test URL security analysis"""
        test_urls = [
            "https://example.com",
            "https://github.com", 
            "http://httpbin.org"
        ]
        
        all_passed = True
        for url in test_urls:
            success, response = self.run_test(
                f"URL Analysis - {url}",
                "POST",
                "analyze",
                200,
                data={"url": url}
            )
            
            if success and response:
                # Verify response structure
                required_fields = ['url', 'https', 'security_headers', 'privacy_score', 'security_score', 'recommendations']
                for field in required_fields:
                    if field not in response:
                        print(f"❌ Missing field in response: {field}")
                        all_passed = False
                    else:
                        print(f"   ✓ {field}: {response.get(field, 'N/A')}")
            else:
                all_passed = False
                
        return all_passed

    def test_bookmarks_crud(self):
        """Test bookmark CRUD operations"""
        # Create bookmark
        bookmark_data = {
            "url": "https://example.com",
            "title": "Example Site",
            "favicon": "",
            "folder": "Test"
        }
        
        success, response = self.run_test(
            "Create Bookmark",
            "POST",
            "bookmarks",
            200,
            data=bookmark_data
        )
        
        if not success:
            return False
            
        bookmark_id = response.get('id')
        if bookmark_id:
            self.created_items['bookmarks'].append(bookmark_id)
        
        # Get bookmarks
        success, response = self.run_test(
            "Get Bookmarks",
            "GET",
            "bookmarks",
            200
        )
        
        if not success:
            return False
            
        # Verify bookmark exists in list
        bookmark_found = any(b.get('id') == bookmark_id for b in response)
        if not bookmark_found:
            print(f"❌ Created bookmark not found in list")
            return False
        
        # Delete bookmark
        success, response = self.run_test(
            "Delete Bookmark",
            "DELETE",
            f"bookmarks/{bookmark_id}",
            200
        )
        
        if success and bookmark_id in self.created_items['bookmarks']:
            self.created_items['bookmarks'].remove(bookmark_id)
            
        return success

    def test_history_crud(self):
        """Test history CRUD operations"""
        # Add history entry
        history_data = {
            "url": "https://test-site.com",
            "title": "Test Site",
            "favicon": ""
        }
        
        success, response = self.run_test(
            "Add History Entry",
            "POST",
            "history",
            200,
            data=history_data
        )
        
        if not success:
            return False
            
        history_id = response.get('id')
        if history_id:
            self.created_items['history'].append(history_id)
        
        # Get history
        success, response = self.run_test(
            "Get History",
            "GET",
            "history",
            200,
            params={"limit": 50}
        )
        
        if not success:
            return False
            
        # Test duplicate URL (should increment visit count)
        success, response = self.run_test(
            "Add Duplicate History Entry",
            "POST",
            "history",
            200,
            data=history_data
        )
        
        if success and response.get('visit_count', 0) > 1:
            print(f"   ✓ Visit count incremented: {response.get('visit_count')}")
        
        # Clear history
        success, response = self.run_test(
            "Clear History",
            "DELETE",
            "history",
            200
        )
        
        if success:
            self.created_items['history'].clear()
            
        return success

    def test_tabs_crud(self):
        """Test tabs CRUD operations"""
        # Create tab
        tab_data = {
            "url": "https://example.org",
            "title": "Example Org",
            "favicon": ""
        }
        
        success, response = self.run_test(
            "Create Tab",
            "POST",
            "tabs",
            200,
            data=tab_data
        )
        
        if not success:
            return False
            
        tab_id = response.get('id')
        if tab_id:
            self.created_items['tabs'].append(tab_id)
        
        # Get tabs
        success, response = self.run_test(
            "Get Tabs",
            "GET",
            "tabs",
            200
        )
        
        if not success:
            return False
            
        # Delete tab
        success, response = self.run_test(
            "Delete Tab",
            "DELETE",
            f"tabs/{tab_id}",
            200
        )
        
        if success and tab_id in self.created_items['tabs']:
            self.created_items['tabs'].remove(tab_id)
            
        return success

    def cleanup_test_data(self):
        """Clean up any remaining test data"""
        print("\n🧹 Cleaning up test data...")
        
        # Clean up bookmarks
        for bookmark_id in self.created_items['bookmarks']:
            try:
                requests.delete(f"{self.api_url}/bookmarks/{bookmark_id}", timeout=10)
            except:
                pass
                
        # Clean up tabs
        for tab_id in self.created_items['tabs']:
            try:
                requests.delete(f"{self.api_url}/tabs/{tab_id}", timeout=10)
            except:
                pass
                
        # Clear history if any entries remain
        if self.created_items['history']:
            try:
                requests.delete(f"{self.api_url}/history", timeout=10)
            except:
                pass

    def run_all_tests(self):
        """Run all API tests"""
        print("🚀 Starting DevBrowser API Tests")
        print(f"Base URL: {self.base_url}")
        print("=" * 50)
        
        try:
            # Test basic connectivity
            if not self.test_root_endpoint():
                print("❌ Root endpoint failed - stopping tests")
                return False
                
            # Test URL analysis (core feature)
            if not self.test_url_analysis():
                print("❌ URL analysis failed - this is a critical feature")
                return False
                
            # Test CRUD operations
            self.test_bookmarks_crud()
            self.test_history_crud() 
            self.test_tabs_crud()
            
        finally:
            self.cleanup_test_data()
        
        # Print results
        print("\n" + "=" * 50)
        print(f"📊 Tests completed: {self.tests_passed}/{self.tests_run}")
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"📈 Success rate: {success_rate:.1f}%")
        
        if success_rate >= 80:
            print("✅ Backend API tests PASSED")
            return True
        else:
            print("❌ Backend API tests FAILED")
            return False

def main():
    tester = DevBrowserAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
