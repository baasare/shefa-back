"""
Order views for ShefaAI Trading Platform.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import Order, Trade
from .serializers import (
    OrderSerializer, OrderListSerializer,
    OrderApprovalSerializer, TradeSerializer
)


class OrderViewSet(viewsets.ModelViewSet):
    """ViewSet for Order CRUD operations."""
    
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return OrderListSerializer
        elif self.action == 'approve_order':
            return OrderApprovalSerializer
        return OrderSerializer
    
    def get_queryset(self):
        """Return orders for authenticated user's portfolios."""
        return Order.objects.filter(
            portfolio__user=self.request.user
        ).select_related('portfolio', 'strategy', 'approved_by')
    
    @action(detail=True, methods=['post'])
    def approve_order(self, request, pk=None):
        """Approve or reject an order (HITL)."""
        order = self.get_object()
        
        if order.status != 'pending_approval':
            return Response(
                {'error': 'Order is not pending approval'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = OrderApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        action_type = serializer.validated_data['action']
        
        if action_type == 'approve':
            order.status = 'approved'
            order.approved_by = request.user
            order.approved_at = timezone.now()
            message = 'Order approved successfully'
        else:
            order.status = 'rejected'
            order.rejection_reason = serializer.validated_data.get('rejection_reason', '')
            message = 'Order rejected'
        
        order.save()
        
        return Response({
            'message': message,
            'order': OrderSerializer(order).data
        })
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an order."""
        order = self.get_object()
        
        if order.status not in ['pending', 'pending_approval', 'submitted']:
            return Response(
                {'error': 'Order cannot be cancelled in current status'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        order.status = 'cancelled'
        order.save()
        
        serializer = self.get_serializer(order)
        return Response({
            'message': 'Order cancelled successfully',
            'order': serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def pending_approval(self, request):
        """Get all orders pending approval."""
        orders = self.get_queryset().filter(status='pending_approval')
        serializer = self.get_serializer(orders, many=True)
        
        return Response({
            'count': orders.count(),
            'orders': serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def by_symbol(self, request):
        """Get orders for a specific symbol."""
        symbol = request.query_params.get('symbol', '').upper()
        
        if not symbol:
            return Response(
                {'error': 'symbol parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        orders = self.get_queryset().filter(symbol=symbol)
        serializer = self.get_serializer(orders, many=True)
        
        return Response({
            'symbol': symbol,
            'orders': serializer.data
        })


class TradeViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for Trade history."""
    
    permission_classes = [IsAuthenticated]
    serializer_class = TradeSerializer
    
    def get_queryset(self):
        """Return trades for authenticated user's portfolios."""
        return Trade.objects.filter(
            portfolio__user=self.request.user
        ).select_related('portfolio', 'strategy', 'order', 'position')
    
    @action(detail=False, methods=['get'])
    def by_symbol(self, request):
        """Get trades for a specific symbol."""
        symbol = request.query_params.get('symbol', '').upper()
        
        if not symbol:
            return Response(
                {'error': 'symbol parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        trades = self.get_queryset().filter(symbol=symbol)
        serializer = self.get_serializer(trades, many=True)
        
        return Response({
            'symbol': symbol,
            'trades': serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def performance(self, request):
        """Get trading performance summary."""
        trades = self.get_queryset()
        
        total_trades = trades.count()
        profitable_trades = trades.filter(realized_pnl__gt=0).count()
        
        total_pnl = sum(
            float(trade.realized_pnl) 
            for trade in trades 
            if trade.realized_pnl
        )
        
        return Response({
            'total_trades': total_trades,
            'profitable_trades': profitable_trades,
            'win_rate': (profitable_trades / total_trades * 100) if total_trades > 0 else 0,
            'total_pnl': total_pnl
        })
