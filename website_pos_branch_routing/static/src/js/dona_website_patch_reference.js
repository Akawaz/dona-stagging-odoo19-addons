/**
 * REFERENCE ONLY - this file is not loaded by the module and changes nothing
 * on its own.
 *
 * The branch/pickup-delivery/date-time picker already lives as inline
 * HTML/CSS/JS embedded directly in the Website page's content (the
 * "#dona-zullee-shop" block), not as a module asset - so this addon cannot
 * patch it automatically on install. Apply the two small changes below by
 * hand, inside that same embedded <script> block, using the Website Builder
 * (Edit -> the HTML block -> Source code).
 *
 * Everything else in the existing widget (branch selection, pickup/delivery,
 * date/time, /dona/order/context POST, product configurator, /shop/cart/add)
 * is left exactly as-is - this module integrates with it, per spec section 20.
 */

/* ------------------------------------------------------------------
 * PATCH 1 - send the per-product comment to the backend (section 10).
 *
 * Today, `addNative()` reads the textarea into
 * `state.product.additionalComments` but never actually transmits it -
 * `/shop/cart/add` has no field for it. Odoo's own cart-add response already
 * returns `line_id` (see `_cart_add()` in addons/website_sale/models/
 * sale_order.py), so send the note right after, using that id.
 *
 * FIND (inside addNative(), right after `await refreshCart();`):
 * ------------------------------------------------------------------ */
//   if(result?.cart_quantity!==undefined)state.cartCount=Number(result.cart_quantity)||0;
//   await refreshCart();
//   closeProduct();
//   toast('Added to cart');

/* REPLACE WITH: */
//   if(result?.cart_quantity!==undefined)state.cartCount=Number(result.cart_quantity)||0;
//   if(result?.line_id && state.product.additionalComments){
//     try{
//       await fetch('/dona/order/line_note',{
//         method:'POST',
//         credentials:'same-origin',
//         headers:{'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'},
//         body:JSON.stringify({line_id:result.line_id,note:state.product.additionalComments})
//       });
//     }catch(e){console.warn('DONA line note sync failed:',e);}
//   }
//   await refreshCart();
//   closeProduct();
//   toast('Added to cart');

/* ------------------------------------------------------------------
 * PATCH 2 (optional, section 16) - prefer Odoo as the source of truth for
 * the branch list, keeping the current hard-coded DONA_RAW_BRANCHES only as
 * a fallback if the endpoint is unreachable.
 *
 * FIND (top-level IIFE, right after `const DONA_LOCATIONS=...` is built):
 * ------------------------------------------------------------------ */
//   const DONA_LOCATIONS=DONA_RAW_BRANCHES.map(branch=>{ ... });

/* ADD RIGHT AFTER IT: */
//   (async () => {
//     try{
//       const r = await fetch('/dona/order/branches',{credentials:'same-origin'});
//       if(!r.ok) return;
//       const serverBranches = await r.json();
//       if(!Array.isArray(serverBranches) || !serverBranches.length) return;
//       serverBranches.forEach(sb=>{
//         const local = DONA_LOCATIONS.find(l=>String(l.id).toUpperCase()===String(sb.code).toUpperCase());
//         if(local){
//           // Keep the richer local data (map coords, hours) but let Odoo's
//           // admin-managed name/address/phone win.
//           local.name = sb.name || local.name;
//           local.posKey = sb.code;
//           local.address = sb.address || local.address;
//           local.phone = sb.phone || local.phone;
//         }
//       });
//     }catch(e){console.warn('DONA branch list backend sync failed, using JS fallback:',e);}
//   })();
