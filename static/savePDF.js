// Detect GST Bill or UPI mode from URL
const urlParams = new URLSearchParams(window.location.search);
const voucherType = urlParams.get("type")?.toLowerCase() || "";
const isGstBill = voucherType.includes("gstbill");
const { jsPDF } = window.jspdf || {};

const justifications = [
    'Diesel purchases were made from local filling stations to ensure generators and machinery at remote or project sites',
    'Labour charges were paid to skilled and unskilled workers engaged on short notice for fabrication, assembly, or repair work.',
    'Consumables and raw materials such as welding rods, fasteners, and basic hardware were procured locally to meet urgent project demands.',
    'Travel expenses included local transport arrangements where Vendors provided hand-written receipts without GST components'
];

const justificationMap = {
    'Diesel purchases': justifications[0],
    'Labour Charges': justifications[1],
    'Consumables and raw materials': justifications[2],
    'Travel expenses': justifications[3]
};

async function fetchVoucherImage(recordId) {
    try {
        const response = await fetch(`/voucher_image/${recordId}`);
        if (!response.ok) {
            throw new Error('Failed to fetch voucher image');
        }
        const blob = await response.blob();
        return await readBlobAsBase64(blob);
    } catch (err) {
        console.warn('Could not fetch voucher image:', err);
        return null;
    }
}

async function fetchStampImage() {
    try {
        // Use absolute path relative to the web root
        const response = await fetch('/static/Bariflostamp.png');
        if (!response.ok) {
            throw new Error('Failed to fetch stamp image');
        }
        const blob = await response.blob();
        return await readBlobAsBase64(blob);
    } catch (err) {
        console.warn('Could not fetch stamp image:', err);
        return null;
    }
}

async function fetchUploadedPDF(recordId) {
    try {
        const response = await fetch(`/get_uploaded_pdf/${recordId}`);
        if (!response.ok) {
            throw new Error('Failed to fetch uploaded PDF');
        }
        const blob = await response.blob();
        const arrayBuffer = await blob.arrayBuffer();
        return new Uint8Array(arrayBuffer);
    } catch (err) {
        console.warn('Could not fetch uploaded PDF:', err);
        return null;
    }
}

function readBlobAsBase64(blob) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
    });
}

function drawHeader(doc, pageWidth) {
    const blueHeight = 30;
    const blackHeight = 5;

    doc.setFillColor(0, 102, 204);
    doc.context2d.beginPath();
    doc.context2d.moveTo(0, blueHeight);
    doc.context2d.bezierCurveTo(
        pageWidth / 4, blueHeight - 10,
        pageWidth * 3 / 4, blueHeight + 10,
        pageWidth, blueHeight
    );
    doc.context2d.lineTo(pageWidth, 0);
    doc.context2d.lineTo(0, 0);
    doc.context2d.closePath();
    doc.context2d.fill();

    doc.setFillColor(0, 0, 0);
    doc.context2d.beginPath();
    doc.context2d.moveTo(0, blueHeight);
    doc.context2d.bezierCurveTo(
        pageWidth / 4, blueHeight + blackHeight,
        pageWidth * 3 / 4, blueHeight + blackHeight,
        pageWidth, blueHeight
    );
    doc.context2d.lineTo(pageWidth, blueHeight + blackHeight);
    doc.context2d.lineTo(0, blueHeight + blackHeight);
    doc.context2d.closePath();
    doc.context2d.fill();

    doc.setFont('times', 'bold');
    doc.setFontSize(16);
    doc.setTextColor(0, 102, 204);
    doc.text('BARIFLO CYBERNETICS PRIVATE LIMITED', pageWidth / 2, blueHeight + blackHeight + 10, { align: 'center' });
    doc.setFontSize(12);
}

function drawFooter(doc, pageNumber, totalPages, pageWidth, pageHeight) {
    doc.setFillColor(0, 102, 204);
    doc.rect(0, pageHeight - 35, pageWidth, 35, 'F');

    doc.setFont('times', 'bold');
    doc.setFontSize(11);
    doc.setTextColor(255, 255, 255);

    const leftX = 10;
    let leftY = pageHeight - 27;
    doc.text('CIN - U74999OR2018PTC029923', leftX, leftY);
    leftY += 6;
    doc.text('Room - 207, TB I-2, KIIT TBI,', leftX, leftY);
    leftY += 6;
    doc.text('Bhubaneswar, Odisha, 751024', leftX, leftY);

    const rightX = pageWidth - 10;
    let rightY = pageHeight - 27;
    doc.text('+91 7328021033, 9777171033', rightX, rightY, { align: 'right' });
    rightY += 6;
    doc.text('mrityunjay.sahu@bariflolabs.com', rightX, rightY, { align: 'right' });

    doc.setFont('times', 'normal');
    doc.setFontSize(9);
    doc.text(`Page ${pageNumber} of ${totalPages}`, pageWidth / 2, pageHeight - 5, { align: 'center' });
}

function readFileAsBase64(fileInput) {
    return new Promise((resolve) => {
        if (fileInput.files && fileInput.files[0]) {
            const reader = new FileReader();
            reader.onload = (e) => resolve(e.target.result);
            reader.onerror = () => resolve(null);
            reader.readAsDataURL(fileInput.files[0]);
        } else {
            resolve(null);
        }
    });
}

async function getImageDimensions(base64) {
    return new Promise((resolve) => {
        const img = new Image();
        img.onload = () => resolve({ width: img.width, height: img.height });
        img.onerror = () => resolve({ width: 0, height: 0 });
        img.src = base64;
    });
}

async function savePDF(recordId, callback) {
    if (typeof callback !== 'function') {
        console.error('❌ Callback must be a function.');
        alert('❌ Internal error: Missing callback function.');
        return;
    }

    if (!jsPDF) {
        console.error('jsPDF not loaded');
        alert('❌ PDF generation library (jsPDF) not loaded. Please check your internet connection or refresh the page.');
        callback(null);
        return;
    }

    try {
        console.log('Starting savePDF for session:', recordId);

        const fullName = document.getElementById('account_name')?.value.trim();
        const voucherTypeInput = document.getElementById('voucher_type')?.value || '';
        const isGstMode = voucherTypeInput === 'gstbill';

        if (!fullName) {
            alert('Please fill the account name field.');
            callback(null);
            return;
        }

        // Get signature data - could be text or image
        let signatureText = document.getElementById('receiver_signature')?.value.trim();
        let signatureImageBase64 = null;
        
        // Check if there's a signature image container (meaning it's a drawn signature)
        const signatureImageContainer = document.getElementById('receiver_signature_container');
        if (signatureImageContainer) {
            // Try to get the actual image from the container
            const signatureImg = signatureImageContainer.querySelector('img');
            if (signatureImg) {
                signatureImageBase64 = signatureImg.src;
            }
            // Even if we can't get the image, we'll still show the text placeholder
        }

        const transactionId = document.getElementById('transaction_id')?.value.trim();
        const amount = document.getElementById('amount')?.value.trim();
        const date = document.getElementById('date')?.value.trim();
        const time = document.getElementById('time')?.value.trim();
        const vendor = document.getElementById('procured_from')?.value.trim();
        const location = document.getElementById('location')?.value.trim();
        const justification = document.getElementById('reason')?.value.trim();
        const receiptInput = document.getElementById('additional_receipt');
        
        if (!transactionId || !amount || !date || !time || !vendor || !location || !justification || !fullName || !signatureText) {
            console.warn('Missing required fields');
            alert('Please fill all required fields.');
            callback(null);
            return;
        }
        
        console.log('Form fields validated successfully');
        
        // Use the permanent stamp instead of the upload field
        const stampBase64 = await fetchStampImage();
        const receiptBase64 = await readFileAsBase64(receiptInput);
        const voucherImageBase64 = await fetchVoucherImage(recordId);
        console.log('Files read:', { stampBase64: !!stampBase64, receiptBase64: !!receiptBase64, voucherImageBase64: !!voucherImageBase64 });

        const doc = new jsPDF('p', 'mm', 'a4');
        const pageWidth = doc.internal.pageSize.getWidth();
        const pageHeight = doc.internal.pageSize.getHeight();

        let totalPages = 2;
        if (voucherImageBase64) totalPages++;
        if (receiptBase64) totalPages++;
        
        const selectedJustification = justificationMap[justification] || '';

        // Page generation with order: Receipt → Voucher → Justification pages
        for (let page = 1; page <= totalPages; page++) {
            if (page > 1) doc.addPage();
            drawHeader(doc, pageWidth);
            drawFooter(doc, page, totalPages, pageWidth, pageHeight);

            if (page === 1 && receiptBase64) {
                // RECEIPT PAGE
                doc.setFont('times', 'bold');
                doc.setFontSize(16);
                doc.text('Attached Receipt', pageWidth / 2, 50, { align: 'center' });

                const marginTop = 60;
                const marginBottom = 50;
                const availableHeight = pageHeight - marginTop - marginBottom;
                const availableWidth = pageWidth - 20;

                doc.addImage(receiptBase64, 'JPEG', 10, marginTop, availableWidth, availableHeight);
            
            } else if ((page === 1 && !receiptBase64 && voucherImageBase64) || (page === 2 && receiptBase64 && voucherImageBase64)) {
                // VOUCHER SNAPSHOT PAGE - CENTERED
                doc.setFont('times', 'bold');
                doc.setFontSize(16);
                doc.text('Voucher Snapshot', pageWidth / 2, 50, { align: 'center' });

                const marginTop = 60;
                const marginBottom = 50;
                const marginHorizontal = 10;
                const availableWidth = pageWidth - 2 * marginHorizontal;
                const availableHeight = pageHeight - marginTop - marginBottom;

                const { width: naturalWidth, height: naturalHeight } = await getImageDimensions(voucherImageBase64);
                if (naturalWidth === 0 || naturalHeight === 0) {
                    console.warn('Invalid voucher image dimensions');
                    doc.text('Error: Unable to load voucher image', pageWidth / 2, pageHeight / 2, { align: 'center' });
                } else {
                    // Calculate scale to fit while maintaining aspect ratio
                    const scale = Math.min(availableWidth / naturalWidth, availableHeight / naturalHeight);
                    const imgWidth = naturalWidth * scale;
                    const imgHeight = naturalHeight * scale;
                    
                    // Center the image
                    const imgX = (pageWidth - imgWidth) / 2;
                    const imgY = marginTop + (availableHeight - imgHeight) / 2;

                    doc.addImage(voucherImageBase64, 'PNG', imgX, imgY, imgWidth, imgHeight, '', 'FAST');
                }

            } else if ((page === 1 && !receiptBase64 && !voucherImageBase64) || 
                      (page === 2 && !voucherImageBase64 && receiptBase64) || 
                      (page === 3 && receiptBase64 && voucherImageBase64) ||
                      (page === 3 && !receiptBase64 && voucherImageBase64)) {
                // MAIN JUSTIFICATION LETTER - FIRST PART
                doc.setFont('times', 'normal');
                doc.setFontSize(12);
                doc.setTextColor(0, 0, 0);

                let y = 70;
                doc.text('To', 20, y);
                doc.text('The Accounts Manager', 20, y += 8);
                doc.text('Bariflo Cybernetics Pvt Ltd', 20, y += 8);
                doc.text('Bhubaneswar, Odisha, 751024', 20, y += 8);
                y += 10;
                doc.setFont('times', 'bold');
                doc.setFontSize(12);
                doc.text('Subject: Justification for Non-GST Bill Submission under Fabrication/Consumable/raw material/travel/contingency.', 20, y, { maxWidth: 170 });
                y += 15;
                doc.setFont('times', 'normal');
                doc.setFontSize(12);
                doc.text('Dear Sir/Madam,', 20, y);
                y += 10;

                const para1 = `I am writing to provide a formal justification for the submission of non-GST bills related to expenses incurred under the following categories: Fabrication/Consumables/Raw Materials/Travel/Contingency: Diesel Purchase/Labour Charges.`;
                doc.text(doc.splitTextToSize(para1, 170), 20, y);
                y += 10;

                doc.setFont('times', 'bold');
                doc.setFontSize(12);
                doc.text(`Transaction ID:`, 20, y += 8);
                doc.setFont('times', 'normal');
                doc.setFontSize(12);
                doc.text(`${transactionId}`, 65, y);

                doc.setFont('times', 'bold');
                doc.setFontSize(12);
                doc.text(`Amount Rs.:`, 20, y += 6);
                doc.setFont('times', 'normal');
                doc.setFontSize(12);
                const cleanAmount = amount.replace(/[^\d.,]/g, '');
                doc.text(`${cleanAmount}`, 65, y);

                doc.setFont('times', 'bold');
                doc.setFontSize(12);
                doc.text(`Date:`, 20, y += 6);
                doc.setFont('times', 'normal');
                doc.setFontSize(12);
                doc.text(`${date}`, 65, y);

                doc.setFont('times', 'bold');
                doc.setFontSize(12);
                doc.text(`Time:`, 20, y += 6);
                doc.setFont('times', 'normal');
                doc.setFontSize(12);
                doc.text(`${time}`, 65, y);

                const para2 = `The transaction was undertaken by me in response to an urgent operational requirement. The items/services were procured from ${vendor}, located ${location}`;
                const para2Part2 = `. These vendors, being small-scale local suppliers, are currently not registered under the GST regime and are therefore unable to issue GST-compliant invoices.`;
                const para3Part3 = `The selection of these vendors was based on their immediate availability, proximity, and reliability, which were crucial given the time-sensitive nature of the requirement. Sourcing from GST-registered vendors would have caused undue delays and hindered critical operations.`;

                doc.text(doc.splitTextToSize(para2, 170), 20, y += 10);
                doc.text(doc.splitTextToSize(para2Part2, 170), 20, y += 10);
                doc.text(doc.splitTextToSize(para3Part3, 170), 20, y += 12);

                y += 25;
                doc.text('To Illustrate:', 20, y);
                y += 6;

                justifications.slice(0, 3).forEach(j => {
                    const isSelected = j === selectedJustification;
                    doc.setFont('times', isSelected ? 'bold' : 'normal');
                    doc.setFontSize(12);
                    doc.setTextColor(isSelected ? 0 : 0, isSelected ? 128 : 0, isSelected ? 0 : 0);
                    doc.text(`• ${j}`, 25, y, { maxWidth: 160 });
                    y += 12;
                });
                doc.setTextColor(0, 0, 0);

            } else {
                // JUSTIFICATION CONTINUATION + SIGNATURE
                let y = 70;
                const fourth = justifications[3];
                const isSelected = fourth === selectedJustification;
                doc.setFont('times', isSelected ? 'bold' : 'normal');
                doc.setFontSize(12);
                doc.setTextColor(isSelected ? 0 : 0, isSelected ? 128 : 0, isSelected ? 0 : 0);
                doc.text(`• ${fourth}`, 20, y, { maxWidth: 170 });
                doc.setTextColor(0, 0, 0);

                doc.setFont('times', 'normal');
                doc.setFontSize(12);
                y += 20;
                const para3 = `All related transactions are supported by valid non-GST invoices, duly signed and acknowledged by the respective vendors. Furthermore, the materials and services received have been verified in terms of quality and quantity by the concerned team members.`;
                doc.text(doc.splitTextToSize(para3, 170), 20, y);

                y += 25;
                const para4 = `In view of the above, I kindly request your consideration for the approval and reimbursement of these non-GST bills under the relevant expense categories.`;
                doc.text(doc.splitTextToSize(para4, 170), 20, y);

                y += 25;
                doc.text('Thank you for your understanding and continued support.', 20, y);

                y += 20;
                doc.text('Sincerely,', 20, y);

                // Handle signature - show image if available, otherwise show text
                if (signatureImageBase64) {
                    // Add signature image
                    doc.setFont('times', 'bold');
                    doc.setFontSize(12);
                    doc.text('Signature:', 20, y += 12);
                    
                    // Get image dimensions and add it to the PDF
                    const { width: imgWidth, height: imgHeight } = await getImageDimensions(signatureImageBase64);
                    if (imgWidth > 0 && imgHeight > 0) {
                        // Scale the image to fit nicely
                        const maxWidth = 80;
                        const maxHeight = 40;
                        const scale = Math.min(maxWidth / imgWidth, maxHeight / imgHeight, 1);
                        const finalWidth = imgWidth * scale;
                        const finalHeight = imgHeight * scale;
                        
                        doc.addImage(signatureImageBase64, 'PNG', 20, y += 5, finalWidth, finalHeight);
                        y += finalHeight + 5;
                    }
                } else {
                    // Add signature text
                    doc.setFont('times', 'italic');
                    doc.setFontSize(18);
                    doc.text(signatureText, 20, y += 12);
                }

                doc.setFont('times', 'bold');
                doc.setFontSize(12);
                doc.text('Your Full Name:', 20, y += 12);
                doc.setFont('times', 'normal');
                doc.setFontSize(12);
                doc.text(fullName, 80, y);

                if (stampBase64) {
                    const imgWidth = 40;
                    const imgHeight = 40;
                    const stampY = pageHeight - imgHeight - 50;
                    const stampX = pageWidth - imgWidth - 20;
                    doc.addImage(stampBase64, 'PNG', stampX, stampY, imgWidth, imgHeight);
                }
            }
        }

        const safeName = fullName.replace(/\s+/g, '_');
        const fileName = `Justification_${safeName}_${Date.now()}.pdf`;
        console.log('Saving PDF as:', fileName);
        
        // Generate PDF as base64
        const pdfBase64 = doc.output('datauristring').split(',')[1];
        console.log('PDF base64 generated, length:', pdfBase64.length);

        // For GST bill mode, we need to handle the voucher image attachment
        if (isGstMode) {
            // If there's an uploaded PDF, we'll modify it to include the voucher image
            if (receiptInput.files.length > 0) {
                const uploadedPdfFile = receiptInput.files[0];
                
                // Create FormData to send both the uploaded PDF and voucher image to server
                const formData = new FormData();
                formData.append('uploadedPdf', uploadedPdfFile);
                formData.append('voucherImage', voucherImageBase64);
                formData.append('recordId', recordId);
                formData.append('transactionId', transactionId);
                
                // Send to server to modify the PDF and return it
                const response = await fetch('/modify_pdf_with_voucher', {
                    method: 'POST',
                    body: formData
                });
                
                if (response.ok) {
                    const blob = await response.blob();
                    
                    // Download the modified PDF
                    const downloadLink = document.createElement('a');
                    downloadLink.href = URL.createObjectURL(blob);
                    downloadLink.download = `GST_Bill_${transactionId}_with_voucher.pdf`;
                    document.body.appendChild(downloadLink);
                    downloadLink.click();
                    downloadLink.remove();
                    
                    // Show message that PDF has been downloaded
                    alert("✅ GST Bill PDF with voucher image downloaded!");
                    
                    // Convert blob to base64 for email
                    const reader = new FileReader();
                    reader.onload = function() {
                        const modifiedPdfBase64 = reader.result.split(',')[1];
                        
                        // Send email with the modified PDF only for GST bill
                        const recipients = [
                            "sethytrinatha25@gmail.com",
                            "sethytrinatha5@gmail.com",
                            "jiteshmohapatra2000@gmail.com"
                        ];
                        
                        fetch('/send_pdf_email', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                pdfBase64: modifiedPdfBase64,
                                fileName: `GST_Bill_${transactionId}_with_voucher.pdf`,
                                recipients
                            })
                        })
                        .then(res => res.json())
                        .then(data => {
                            if (data.success) {
                                alert('✅ Mail sent successfully!');
                            } else {
                                alert('⚠️ Failed to send email.');
                            }
                            callback({ pdfBase64: modifiedPdfBase64, fileName: `GST_Bill_${transactionId}_with_voucher.pdf` });
                        })
                        .catch(err => {
                            console.error('Error sending PDF email:', err);
                            alert('❌ Error sending email.');
                            callback({ pdfBase64: modifiedPdfBase64, fileName: `GST_Bill_${transactionId}_with_voucher.pdf` });
                        });
                    };
                    reader.readAsDataURL(blob);
                } else {
                    // Fallback to original behavior
                    const downloadLink = document.createElement('a');
                    downloadLink.href = URL.createObjectURL(uploadedPdfFile);
                    downloadLink.download = `GST_Bill_${transactionId}.pdf`;
                    document.body.appendChild(downloadLink);
                    downloadLink.click();
                    downloadLink.remove();
                    
                    alert("✅ Uploaded GST Bill PDF downloaded!");
                    callback(null);
                }
            } else {
                // If no PDF was uploaded, save the generated PDF
                doc.save(fileName);
                
                // Show message that PDF has been downloaded
                alert("✅ Justification PDF downloaded!");
                
                // Send email with the generated PDF for GST bill after download
                setTimeout(() => {
                    const recipients = [
                        "sethytrinatha25@gmail.com",
                        "sethytrinatha5@gmail.com",
                        "jiteshmohapatra2000@gmail.com"
                    ];

                    fetch('/send_pdf_email', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            pdfBase64: pdfBase64,
                            fileName: fileName,
                            recipients
                        })
                    })
                    .then(res => res.json())
                    .then(data => {
                        if (data.success) {
                            alert('✅ Mail sent successfully!');
                        } else {
                            alert('⚠️ Failed to send email.');
                        }
                        callback({ pdfBase64: pdfBase64, fileName: fileName });
                    })
                    .catch(err => {
                        console.error('Error sending PDF email:', err);
                        alert('❌ Error sending email.');
                        callback({ pdfBase64: pdfBase64, fileName: fileName });
                    });
                }, 500); // Reduced delay to ensure download completes
            }
        } else {
            // For non-GST mode, just download the generated PDF as before
            doc.save(fileName);
            
            // Show message that PDF has been downloaded
            alert("✅ Justification PDF downloaded!");
            
            // Send email with the generated PDF after download
            setTimeout(() => {
                const recipients = [
                    "sethytrinatha25@gmail.com",
                    "sethytrinatha5@gmail.com",
                    "jiteshmohapatra2000@gmail.com"
                ];

                fetch('/send_pdf_email', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        pdfBase64: pdfBase64,
                        fileName: fileName,
                        recipients
                    })
                })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        alert('✅ Mail sent successfully!');
                    } else {
                        alert('⚠️ Failed to send email.');
                    }
                    callback({ pdfBase64: pdfBase64, fileName: fileName });
                })
                .catch(err => {
                    console.error('Error sending PDF email:', err);
                    alert('❌ Error sending email.');
                    callback({ pdfBase64: pdfBase64, fileName: fileName });
                });
            }, 500); // Reduced delay to ensure download completes
        }
    } catch (err) {
        console.error('Error generating PDF:', err);
        alert(`❌ Failed to generate PDF: ${err.message}`);
        callback(null);
    }
}
