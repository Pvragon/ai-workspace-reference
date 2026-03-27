/**
 * Starter Template Generator — Apps Script functions for creating
 * Google Doc starter templates by copying and modifying the Pvragon base.
 *
 * Copy-and-modify approach:
 *   - Copy the existing Pvragon letterhead template (which has positioned
 *     images, styled headers, and page layout that can't be created via API)
 *   - Replace brand-specific content: address, email, logo images, fonts
 *
 * NOTE: Auto-updating page numbers (AutoText) cannot be inserted by ANY
 * Google API. The shared page-number template is brand-independent and
 * reused across all brands.
 */

// Pvragon letterhead template — the base for all brand letterheads
var PVRAGON_LETTERHEAD_TEMPLATE_ID = '1R_mBGvrZfOdAz8bkFWtr4Rn_rsfJqU0q0VClf7YDV-A';

// Positioned object IDs in the Pvragon template (icon + wordmark)
var PVRAGON_LOGO_ICON_ID = 'kix.k96i0bjq66y4';
var PVRAGON_LOGO_WORDMARK_ID = 'kix.r05dpymptrp9';

/**
 * Create a letterhead starter template for a new brand by copying the
 * Pvragon template and replacing brand-specific content.
 *
 * What gets replaced:
 *   - Header address text → new brand's address/contact info
 *   - Header font → brand's primary font
 *   - Positioned logo images → new brand's logo (single centered image)
 *
 * After creation, the user should review the template and iterate:
 *   - Verify logo sizing (images with internal padding may appear small)
 *   - Adjust logo position if needed
 *   - Confirm font and text styling
 *
 * @param {string} brandName - Human-readable brand name (e.g., "RideCare")
 * @param {Object} companyInfo - { address, email, phone, website }
 * @param {Object} brandStyle - { primaryFont } — font name for the header
 * @param {Object} logoConfig - { driveFileId, widthPt, heightPt } — logo file already in Drive
 *   If null, Pvragon logos are deleted and no replacement is inserted.
 *   widthPt/heightPt default to 150/95 if not specified.
 * @param {string} targetFolderId - Google Drive folder ID to move the template into
 * @returns {Object} { documentId, documentUrl, note }
 */
function createLetterheadTemplate(brandName, companyInfo, brandStyle, logoConfig, targetFolderId) {
  // Phase 1: Copy the Pvragon letterhead template
  var title = brandName + ' — Letterhead Starter Template';
  var copy = Drive.Files.copy(
    { title: title },
    PVRAGON_LETTERHEAD_TEMPLATE_ID
  );
  var docId = copy.id;

  // Phase 2: Delete the Pvragon positioned logos
  Docs.Documents.batchUpdate({
    requests: [
      { deletePositionedObject: { objectId: PVRAGON_LOGO_ICON_ID } },
      { deletePositionedObject: { objectId: PVRAGON_LOGO_WORDMARK_ID } }
    ]
  }, docId);

  // Phase 3: Insert the new brand's logo as an inline image in the centered header paragraph
  // Using inline image (not positioned) so Google Docs centers it naturally with the paragraph
  var logoNote = 'No logo provided — header has text only. Add logo manually or re-run with logoConfig.';

  if (logoConfig && logoConfig.driveFileId) {
    var logoUrl = 'https://drive.google.com/uc?id=' + logoConfig.driveFileId;
    var response = UrlFetchApp.fetch(logoUrl);
    var logoBlob = response.getBlob().setContentTypeFromExtension().setName(brandName.toLowerCase() + '-logo.png');

    var doc = DocumentApp.openById(docId);
    var header = doc.getHeader();

    if (header) {
      // The first paragraph (from the Pvragon template) is centered — insert inline image there
      var firstPara = header.getChild(0);
      if (firstPara && firstPara.getType() === DocumentApp.ElementType.PARAGRAPH) {
        var para = firstPara.asParagraph();
        // Clear any existing text in this paragraph
        para.clear();
        para.setAlignment(DocumentApp.HorizontalAlignment.CENTER);

        // Insert logo as inline image — centered paragraph handles centering
        var img = para.appendInlineImage(logoBlob);

        // Set size
        var logoWidth = (logoConfig.widthPt && logoConfig.widthPt > 0) ? logoConfig.widthPt : 150;
        var logoHeight = (logoConfig.heightPt && logoConfig.heightPt > 0) ? logoConfig.heightPt : 95;
        img.setWidth(logoWidth);
        img.setHeight(logoHeight);
      }
    }

    doc.saveAndClose();
    logoNote = 'Logo inserted (' + logoWidth + 'x' + logoHeight + 'pt, centered inline). Review sizing — images with internal padding may appear smaller than expected.';
  }

  // Phase 4: Replace the address text and update fonts via Advanced Service
  var docData = Docs.Documents.get(docId);
  var defaultHeaderId = docData.documentStyle.defaultHeaderId;

  if (defaultHeaderId) {
    var headerContent = docData.headers[defaultHeaderId].content;

    // Find the address paragraph (contains "10796 Montego" from Pvragon template)
    var addressStartIndex = -1;
    var addressEndIndex = -1;

    for (var i = 0; i < headerContent.length; i++) {
      var para = headerContent[i].paragraph;
      if (!para) continue;

      for (var j = 0; j < para.elements.length; j++) {
        var elem = para.elements[j];
        if (elem.textRun && elem.textRun.content.indexOf('10796 Montego') >= 0) {
          addressStartIndex = para.elements[0].startIndex;
          addressEndIndex = headerContent[i].endIndex - 1;
          break;
        }
      }
      if (addressStartIndex >= 0) break;
    }

    var requests = [];

    if (addressStartIndex >= 0 && addressEndIndex > addressStartIndex) {
      // Build new address line: address | phone | email (all pipe-separated)
      var parts = [];
      if (companyInfo.address) parts.push(companyInfo.address);
      if (companyInfo.phone) parts.push(companyInfo.phone);
      if (companyInfo.email) parts.push(companyInfo.email);
      var newAddressLine = parts.join(' | ');

      // Delete old, insert new
      requests.push({
        deleteContentRange: {
          range: { segmentId: defaultHeaderId, startIndex: addressStartIndex, endIndex: addressEndIndex }
        }
      });

      requests.push({
        insertText: {
          location: { segmentId: defaultHeaderId, index: addressStartIndex },
          text: newAddressLine
        }
      });

      // Style: centered, 10pt, brand font
      var newEndIndex = addressStartIndex + newAddressLine.length;
      requests.push({
        updateTextStyle: {
          textStyle: {
            fontSize: { magnitude: 10, unit: 'PT' },
            weightedFontFamily: { fontFamily: (brandStyle && brandStyle.primaryFont) || 'Lato' }
          },
          range: { segmentId: defaultHeaderId, startIndex: addressStartIndex, endIndex: newEndIndex },
          fields: 'fontSize,weightedFontFamily'
        }
      });
    }

    // Update title paragraph font if different from Lato
    if (brandStyle && brandStyle.primaryFont && brandStyle.primaryFont !== 'Lato') {
      var titlePara = headerContent[0];
      if (titlePara && titlePara.paragraph) {
        var titleStart = titlePara.paragraph.elements[0].startIndex || 0;
        var titleEnd = titlePara.endIndex - 1;
        if (titleEnd > titleStart) {
          requests.push({
            updateTextStyle: {
              textStyle: { weightedFontFamily: { fontFamily: brandStyle.primaryFont } },
              range: { segmentId: defaultHeaderId, startIndex: titleStart, endIndex: titleEnd },
              fields: 'weightedFontFamily'
            }
          });
        }
      }
    }

    if (requests.length > 0) {
      Docs.Documents.batchUpdate({ requests: requests }, docId);
    }
  }

  // Phase 5: Move to target folder if specified
  if (targetFolderId) {
    moveFileToFolder_(docId, targetFolderId);
  }

  return {
    documentId: docId,
    documentUrl: 'https://docs.google.com/document/d/' + docId + '/edit',
    note: logoNote + ' Please review the template before finalizing.'
  };
}

/**
 * Move a file to a target folder, removing it from its current parent(s).
 * @private
 */
function moveFileToFolder_(fileId, targetFolderId) {
  var file = DriveApp.getFileById(fileId);
  var folder = DriveApp.getFolderById(targetFolderId);
  folder.addFile(file);

  var parents = file.getParents();
  while (parents.hasNext()) {
    var parent = parents.next();
    if (parent.getId() !== targetFolderId) {
      parent.removeFile(file);
    }
  }
}

/**
 * Test function — verifies clasp roundtrip works.
 */
function hello() {
  return 'clasp roundtrip works';
}
