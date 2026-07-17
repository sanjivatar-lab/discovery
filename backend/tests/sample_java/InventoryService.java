package com.example.orders;

@Service
public class InventoryService {

    private int minimumStockThreshold = 5;

    public boolean checkAvailability(String sku, int quantity) {
        int available = lookupStock(sku);
        if (available < quantity) {
            return false;
        }
        return true;
    }

    public void reserveStock(String sku, int quantity) {
        int available = lookupStock(sku);
        if (available - quantity < minimumStockThreshold) {
            notifyLowStock(sku);
        }
    }

    private int lookupStock(String sku) {
        return sku.length() * 10;
    }

    private void notifyLowStock(String sku) {
        System.out.println("Low stock warning for " + sku);
    }
}
