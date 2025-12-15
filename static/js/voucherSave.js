//    // Original saveVoucher function
//     function saveVoucher() {
//         const voucherType = document.getElementById('voucher_type').value;
//         const form = document.body;

//         html2canvas(form).then(canvas => {
//             const imageData = canvas.toDataURL('image/png');

//             const formData = new FormData();
//             formData.append('image_data', imageData);
//             formData.append('slno', document.getElementById('slno').value);
//             formData.append('date', document.getElementById('date').value);
//             formData.append('account_name', document.getElementById('account_name').value);
//             formData.append('debit', document.getElementById('debit').value);
//             formData.append('credit', document.getElementById('credit').value);
//             formData.append('amount', document.getElementById('amount').value);
//             formData.append('time', document.getElementById('time').value);
//             formData.append('reason', document.getElementById('reason').value);
//             formData.append('procured_from', document.getElementById('procured_from').value);
//             formData.append('location', document.getElementById('location').value);
//             formData.append('location_lat', document.getElementById('location_lat').value);
//             formData.append('location_lng', document.getElementById('location_lng').value);
//             // Use user's e-signature if available, otherwise use the entered one
//             // Handle both text and image signature displays
//             let finalSignature = '';
//             const signatureTextInput = document.getElementById('receiver_signature');
//             const signatureImageContainer = document.getElementById('receiver_signature_container');
            
//             if (signatureImageContainer) {
//                 // It's a drawn signature, use the placeholder text
//                 finalSignature = '[Drawn Signature]';
//             } else if (signatureTextInput) {
//                 // It's a text signature
//                 const userSignature = signatureTextInput.getAttribute('data-user-signature') || '';
//                 const enteredSignature = signatureTextInput.value;
//                 finalSignature = userSignature || enteredSignature;
//             }
            
//             formData.append('receiver_signature', finalSignature);
//             formData.append('transaction_id', document.getElementById('transaction_id').value);
//             formData.append('voucher_type', voucherType);

//             const fileInput1 = document.getElementById('additional_receipt');
//             if (fileInput1.files.length > 0) {
//                 formData.append('additional_receipt', fileInput1.files[0]);
//             }

//             fetch(`/save_voucher`, {
//                 method: 'POST',
//                 body: formData
//             })
//             .then(resp => {
//                 if (!resp.ok) throw new Error("Server error");
//                 return resp.json();
//             })
//             .then(result => {
//                 if (!result.record_id) {
//                     throw new Error("No record ID returned from server.");
//                 }

//                 fetch(`/voucher_image/${result.record_id}`)
//                     .then(imgResp => {
//                         if (!imgResp.ok) throw new Error("Failed to fetch voucher image.");
//                         return imgResp.blob();
//                     })
//                     .then(blob => {
//                         const imageLink = document.createElement('a');
//                         imageLink.href = URL.createObjectURL(blob);
//                         imageLink.download = "voucher.png";
//                         document.body.appendChild(imageLink);
//                         imageLink.click();
//                         imageLink.remove();

//                         savePDF(result.record_id, () => {
//                             if (voucherType === 'gstbill') {
//                                 alert("✅ GST Bill voucher and PDF downloaded!");
//                             } else {
//                                 alert("✅ Voucher saved and PDF downloaded!");
//                             }
//                         });
//                     })
//                     .catch(imgErr => {
//                         console.error(imgErr);
//                         alert("⚠️ Voucher saved, but image fetch failed.");
//                         savePDF(result.record_id, () => {
//                             if (voucherType === 'gstbill') {
//                                 alert("✅ GST Bill PDF downloaded!");
//                             } else {
//                                 alert("✅ Voucher saved and PDF downloaded!");
//                             }
//                         });
//                     });
//             })
//             .catch(err => {
//                 console.error(err);
//                 alert("❌ Failed to save voucher.");
//             });

//         });
//     }

// Original saveVoucher function
    function saveVoucher() {
        const voucherType = document.getElementById('voucher_type').value;
        const form = document.body;

        html2canvas(form).then(canvas => {
            const imageData = canvas.toDataURL('image/png');

            const formData = new FormData();
            formData.append('image_data', imageData);
            formData.append('slno', document.getElementById('slno').value);
            formData.append('date', document.getElementById('date').value);
            formData.append('account_name', document.getElementById('account_name').value);
            formData.append('debit', document.getElementById('debit').value);
            formData.append('credit', document.getElementById('credit').value);
            formData.append('amount', document.getElementById('amount').value);
            formData.append('time', document.getElementById('time').value);
            formData.append('reason', document.getElementById('reason').value);
            formData.append('procured_from', document.getElementById('procured_from').value);
            formData.append('location', document.getElementById('location').value);
            formData.append('location_lat', document.getElementById('location_lat').value);
            formData.append('location_lng', document.getElementById('location_lng').value);
            // Use user's e-signature if available, otherwise use the entered one
            // Handle both text and image signature displays
            let finalSignature = '';
            const signatureTextInput = document.getElementById('receiver_signature');
            const signatureImageContainer = document.getElementById('receiver_signature_container');
            
            if (signatureImageContainer) {
                // It's a drawn signature, use the placeholder text
                finalSignature = '[Drawn Signature]';
            } else if (signatureTextInput) {
                // It's a text signature
                const userSignature = signatureTextInput.getAttribute('data-user-signature') || '';
                const enteredSignature = signatureTextInput.value;
                finalSignature = userSignature || enteredSignature;
            }
            
            formData.append('receiver_signature', finalSignature);
            formData.append('transaction_id', document.getElementById('transaction_id').value);
            formData.append('voucher_type', voucherType);

            const fileInput1 = document.getElementById('additional_receipt');
            if (fileInput1.files.length > 0) {
                formData.append('additional_receipt', fileInput1.files[0]);
            }

            fetch(`/save_voucher`, {
                method: 'POST',
                body: formData
            })
            .then(resp => {
                if (!resp.ok) throw new Error("Server error");
                return resp.json();
            })
            .then(result => {
                if (!result.record_id) {
                    throw new Error("No record ID returned from server.");
                }

                fetch(`/voucher_image/${result.record_id}`)
                    .then(imgResp => {
                        if (!imgResp.ok) throw new Error("Failed to fetch voucher image.");
                        return imgResp.blob();
                    })
                    .then(blob => {
                        const imageLink = document.createElement('a');
                        imageLink.href = URL.createObjectURL(blob);
                        imageLink.download = "voucher.png";
                        document.body.appendChild(imageLink);
                        imageLink.click();
                        imageLink.remove();

                        savePDF(result.record_id, (pdfResult) => {
                            // PDF download and email sending are handled in savePDF function
                            // No need to show additional alerts here
                            if (!pdfResult) {
                                console.log("PDF generation may have failed");
                            }
                        });
                    })
                    .catch(imgErr => {
                        console.error(imgErr);
                        alert("⚠️ Voucher saved, but image fetch failed.");
                        savePDF(result.record_id, (pdfResult) => {
                            // PDF download and email sending are handled in savePDF function
                            // No need to show additional alerts here
                            if (!pdfResult) {
                                console.log("PDF generation may have failed");
                            }
                        });
                    });
            })
            .catch(err => {
                console.error(err);
                alert("❌ Failed to save voucher.");
            });

        });
    }