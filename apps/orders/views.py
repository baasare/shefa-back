"""
Order views for ShefaFx Trading Platform.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import sentry_sdk

from apps.orders.models import Order, Trade
from apps.orders.serializers import (
    OrderSerializer, OrderListSerializer,
    OrderApprovalSerializer, TradeSerializer
)
from apps.orders.services import (
    approve_order_with_audit,
    reject_order_with_audit,
    cancel_order_with_audit,
    get_order_audit_history
)


def capture_order_context(order: Order):
    """Add order context to Sentry for error tracking."""
    sentry_sdk.set_context("order", {
        "order_id": str(order.id),
        "symbol": order.symbol,
        "side": order.side,
        "type": order.type,
        "status": order.status,
        "quantity": order.quantity,
        "limit_price": float(order.limit_price) if order.limit_price else None,
        "filled_qty": order.filled_qty,
        "portfolio_id": order.portfolio_id,
        "broker_order_id": order.broker_order_id,
    })


class OrderViewSet(viewsets.ModelViewSet):
    """ViewSet for Order CRUD operations."""

    permission_classes = [IsAuthenticated]

    def handle_view_exception(self, exc, order=None):
        """Handle exceptions with Sentry context capture."""
        if order:
            capture_order_context(order)
        sentry_sdk.set_user({"id": self.request.user.id, "email": self.request.user.email})
        sentry_sdk.capture_exception(exc)

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
        """Approve or reject an order (HITL) with audit logging."""
        try:
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
                # Use audit-enabled service function
                success, error = approve_order_with_audit(
                    order,
                    request.user,
                    request=request
                )

                if not success:
                    return Response(
                        {'error': error},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                message = 'Order approved successfully'
            else:
                # Use audit-enabled service function
                reason = serializer.validated_data.get('rejection_reason', '')
                success, error = reject_order_with_audit(
                    order,
                    request.user,
                    reason=reason,
                    request=request
                )

                if not success:
                    return Response(
                        {'error': error},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                message = 'Order rejected'

            # Reload order to get updated data
            order.refresh_from_db()

            return Response({
                'message': message,
                'order': OrderSerializer(order).data
            })

        except Exception as e:
            self.handle_view_exception(e, order if 'order' in locals() else None)
            return Response(
                {'error': 'Internal server error processing order approval'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an order with audit logging."""
        order = self.get_object()

        if order.status not in ['pending', 'pending_approval', 'submitted']:
            return Response(
                {'error': 'Order cannot be cancelled in current status'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get cancellation reason from request
        reason = request.data.get('reason', 'User requested cancellation')

        # Use audit-enabled service function
        success, error = cancel_order_with_audit(
            order,
            request.user,
            reason=reason,
            request=request
        )

        if not success:
            return Response(
                {'error': error},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Reload order to get updated data
        order.refresh_from_db()

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

    @action(detail=True, methods=['get'])
    def audit_trail(self, request, pk=None):
        """Get complete audit trail for an order."""
        order = self.get_object()

        # Get audit history using service function
        audit_history = get_order_audit_history(order)

        return Response({
            'order_id': str(order.id),
            'symbol': order.symbol,
            'audit': audit_history,
            'total_events': len(audit_history)
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
