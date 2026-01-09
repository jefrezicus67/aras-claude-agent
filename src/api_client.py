"""
Generic API Client for RESTful operations
Created by D. Theoden
Date: June 12, 2025
Updated: January 08, 2026 - Added update, upsert, and delete operations
"""

import requests
import json
from .auth import get_bearer_token
from .config import URL

class APIClient:
    def __init__(self):
        self.token = None
        self.url = URL
        self.odata_url = f"{URL}/Server/Odata"  # Aras OData endpoint

    def authenticate(self):
        """Authenticate with the API and store the token."""
        try:
            self.token = get_bearer_token()
            return True
        except Exception as error:
            import sys
            print(f"Authentication error: {error}", file=sys.stderr)
            return False

    def get_items(self, endpoint, expand=None, filter_param=None, select=None):
        """Get items from Aras OData API."""
        try:
            if not self.token:
                self.authenticate()

            # Build OData URL - endpoint should be an ItemType like 'Part', 'Document', etc.
            api_url = f"{self.odata_url}/{endpoint}"
            params = []
            
            if expand:
                params.append(f"$expand={expand}")
            if filter_param:
                params.append(f"$filter={filter_param}")
            if select:
                params.append(f"$select={select}")
            
            if params:
                api_url += "?" + "&".join(params)

            response = requests.get(
                api_url,
                headers={
                    'Accept': 'application/json',
                    'Authorization': f'Bearer {self.token}'
                }
            )
            response.raise_for_status()

            return response.json()
        except Exception as error:
            import sys
            print(f"Error getting items: {error}", file=sys.stderr)
            raise error

    def create_item(self, endpoint, data):
        """Create a new item using Aras OData API."""
        try:
            if not self.token:
                self.authenticate()

            response = requests.post(
                f"{self.odata_url}/{endpoint}",
                json=data,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Authorization': f'Bearer {self.token}'
                }
            )
            response.raise_for_status()

            return response.json()
        except Exception as error:
            import sys
            print(f"Error creating item: {error}", file=sys.stderr)
            raise error

    def update_item(self, endpoint, item_id, data, action='edit', return_minimal=False):
        """
        Update an existing item using Aras OData API.
        
        Args:
            endpoint: ItemType name (e.g., 'Part', 'Document')
            item_id: The ID of the item to update
            data: Dictionary containing the properties to update
            action: The Aras action to use ('edit', 'update', 'lock', 'unlock')
            return_minimal: If True, returns 204 No Content on success
        
        Returns:
            Updated item data or None if return_minimal=True
        """
        try:
            if not self.token:
                self.authenticate()

            # Add the @aras.action annotation if using a specific action
            if action and action != 'edit':
                data['@aras.action'] = action

            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': f'Bearer {self.token}'
            }
            
            if return_minimal:
                headers['Prefer'] = 'return=minimal'

            response = requests.patch(
                f"{self.odata_url}/{endpoint}('{item_id}')",
                json=data,
                headers=headers
            )
            response.raise_for_status()

            # Return None for 204 No Content
            if response.status_code == 204:
                return None
            
            return response.json()
        except Exception as error:
            import sys
            print(f"Error updating item: {error}", file=sys.stderr)
            raise error

    def update_property(self, endpoint, item_id, property_name, value, return_minimal=False):
        """
        Update a single property of an item using PUT.
        
        Args:
            endpoint: ItemType name (e.g., 'Part', 'Document')
            item_id: The ID of the item to update
            property_name: Name of the property to update
            value: New value for the property
            return_minimal: If True, returns 204 No Content on success
        
        Returns:
            Updated property or None if return_minimal=True
        """
        try:
            if not self.token:
                self.authenticate()

            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': f'Bearer {self.token}'
            }
            
            if return_minimal:
                headers['Prefer'] = 'return=minimal'

            response = requests.put(
                f"{self.odata_url}/{endpoint}('{item_id}')/{property_name}",
                json={'value': value},
                headers=headers
            )
            response.raise_for_status()

            if response.status_code == 204:
                return None
            
            return response.json()
        except Exception as error:
            import sys
            print(f"Error updating property: {error}", file=sys.stderr)
            raise error

    def upsert_item(self, endpoint, item_id, data, return_minimal=False):
        """
        Upsert an item (create if doesn't exist, update if exists) using merge action.
        
        Args:
            endpoint: ItemType name (e.g., 'Part', 'Document')
            item_id: The ID of the item to upsert
            data: Dictionary containing the item properties
            return_minimal: If True, returns 204 No Content on success
        
        Returns:
            Item data or None if return_minimal=True
        """
        try:
            if not self.token:
                self.authenticate()

            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': f'Bearer {self.token}',
                'If-Match': '*'  # Required for upsert/merge operation
            }
            
            if return_minimal:
                headers['Prefer'] = 'return=minimal'

            response = requests.patch(
                f"{self.odata_url}/{endpoint}('{item_id}')",
                json=data,
                headers=headers
            )
            response.raise_for_status()

            if response.status_code == 204:
                return None
            
            return response.json()
        except Exception as error:
            import sys
            print(f"Error upserting item: {error}", file=sys.stderr)
            raise error

    def delete_item(self, endpoint, item_id, action='delete', return_minimal=True):
        """
        Delete an item using Aras OData API.
        
        Args:
            endpoint: ItemType name (e.g., 'Part', 'Document')
            item_id: The ID of the item to delete
            action: 'delete' (delete all versions) or 'purge' (delete single version)
            return_minimal: If True, returns 204 No Content on success
        
        Returns:
            None (always returns 204 No Content on success)
        """
        try:
            if not self.token:
                self.authenticate()

            headers = {
                'Authorization': f'Bearer {self.token}'
            }

            # For purge action, need to send it in the request body
            if action == 'purge':
                headers['Content-Type'] = 'application/json'
                if return_minimal:
                    headers['Prefer'] = 'return=minimal'
                
                response = requests.delete(
                    f"{self.odata_url}/{endpoint}('{item_id}')",
                    json={'@aras.action': 'purge'},
                    headers=headers
                )
            else:
                # Standard delete
                response = requests.delete(
                    f"{self.odata_url}/{endpoint}('{item_id}')",
                    headers=headers
                )
            
            response.raise_for_status()
            return None  # Delete always returns 204 No Content
        except Exception as error:
            import sys
            print(f"Error deleting item: {error}", file=sys.stderr)
            raise error

    def delete_relationship(self, endpoint, item_id, relationship_name, relationship_id):
        """
        Delete a relationship from an item.
        
        Args:
            endpoint: ItemType name (e.g., 'Part', 'Document')
            item_id: The ID of the source item
            relationship_name: Name of the relationship (e.g., 'Part_CAD')
            relationship_id: The ID of the relationship item to delete
        
        Returns:
            None (always returns 204 No Content on success)
        """
        try:
            if not self.token:
                self.authenticate()

            response = requests.delete(
                f"{self.odata_url}/{endpoint}('{item_id}')/{relationship_name}/$ref?$id={relationship_name}('{relationship_id}')",
                headers={
                    'Authorization': f'Bearer {self.token}'
                }
            )
            response.raise_for_status()
            return None
        except Exception as error:
            import sys
            print(f"Error deleting relationship: {error}", file=sys.stderr)
            raise error

    def clear_item_property(self, endpoint, item_id, property_name):
        """
        Clear/null an item property reference.
        
        Args:
            endpoint: ItemType name (e.g., 'Part', 'Document')
            item_id: The ID of the item
            property_name: Name of the property to clear
        
        Returns:
            None (always returns 204 No Content on success)
        """
        try:
            if not self.token:
                self.authenticate()

            response = requests.delete(
                f"{self.odata_url}/{endpoint}('{item_id}')/{property_name}/$ref",
                headers={
                    'Authorization': f'Bearer {self.token}'
                }
            )
            response.raise_for_status()
            return None
        except Exception as error:
            import sys
            print(f"Error clearing property: {error}", file=sys.stderr)
            raise error

    def call_method(self, method_name, data):
        """Call an Aras server method."""
        try:
            if not self.token:
                self.authenticate()

            # Aras methods are called via OData actions
            response = requests.post(
                f"{self.odata_url}/method.{method_name}",
                json=data,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Authorization': f'Bearer {self.token}'
                }
            )
            response.raise_for_status()

            return response.json()
        except Exception as error:
            import sys
            print(f"Error calling method {method_name}: {error}", file=sys.stderr)
            raise error

    def get_list(self, list_id, expand=None):
        """Get list data from Aras API."""
        try:
            if not self.token:
                self.authenticate()

            # Aras lists are accessed via List ItemType
            list_url = f"{self.odata_url}/List('{list_id}')"
            if expand:
                list_url += f"?$expand={expand}"

            response = requests.get(
                list_url,
                headers={
                    'Accept': 'application/json',
                    'Authorization': f'Bearer {self.token}'
                }
            )
            response.raise_for_status()

            return response.json()
        except Exception as error:
            import sys
            print(f"Error getting list {list_id}: {error}", file=sys.stderr)
            raise error
